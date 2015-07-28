#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Copyright (c) 2015, Marcos (Feirlane) López <feirlane@gmail.com>
# All rights reserved.

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:

#   * Redistributions of source code must retain the above copyright notice, this
#     list of conditions and the following disclaimer.

#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions and the following disclaimer in the documentation
#     and/or other materials provided with the distribution.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from __future__ import print_function
from bs4 import BeautifulSoup
import datetime
import spynner

import httplib2
import os

from apiclient import discovery
import oauth2client
from oauth2client import client
from oauth2client import tools

import sys

try:
    import argparse
    p = argparse.ArgumentParser(parents=[tools.argparser])
    p.add_argument('calendarId',
                   help='Calendar Id where to insert the events\n'
                   + 'You can get it from the iCal URL on google '
                   + 'calendar\nand it looks like this:\n'
                   + 'qkvodipqv8d2mp09uc80a05b0c@group.calendar.google.com')
    flags = p.parse_args()
except ImportError:
    flags = None

SCOPES = 'https://www.googleapis.com/auth/calendar'
CLIENT_SECRET_FILE = 'client_secret.json'
APPLICATION_NAME = 'Akademy BoF Google Calendar synchronizer'


class WikiEvent:

    def __init__(self, startDateTime, location, subject, comments):
        self.startDateTime = startDateTime
        self.endDateTime = None
        self.location = location
        self.subject = subject
        self.comments = comments
        self.duration = 1

    def timeToStr(self, dt):
        return dt.strftime('%Y-%m-%dT%H:%M:00+02:00')

    def startTimeStr(self):
        return self.timeToStr(self.startDateTime)

    def endTimeStr(self):
        if not self.endDateTime:
            self.endDateTime = (self.startDateTime
                                + datetime.timedelta(hours=self.duration))
        return self.timeToStr(self.endDateTime)


def get_credentials():
    """Gets valid user credentials from storage.

    If nothing has been stored, or if the stored credentials are invalid,
    the OAuth2 flow is completed to obtain the new credentials.

    Returns:
        Credentials, the obtained credential.
    """
    home_dir = os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.credentials')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir,
                                   'calendar-quickstart.json')

    store = oauth2client.file.Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = APPLICATION_NAME
        if flags:
            credentials = tools.run_flow(flow, store, flags)
        else:  # Needed only for compatability with Python 2.6
            credentials = tools.run(flow, store)
        print('Storing credentials to', credential_path)
    return credentials


def getGCalEvents(service):
    now = datetime.datetime(2015, 7, 27, 0, 0, 0).isoformat() + 'Z'
    eventsResult = service.events().list(
        calendarId=flags.calendarId,
        timeMin=now,
        maxResults=100,
        singleEvents=True,
        orderBy='startTime').execute()
    return eventsResult.get('items', [])


def getWikiEvents():
    DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    #  Name of the events we don't want on the calendar
    SKIP = ['Lunch', 'Daytrip']

    currentDate = datetime.date(2015, 7, 27)

    browser = spynner.Browser(
        headers=[('User-agent',
                  'Mozilla/5.0 (X11; Linux x86_64; rv:39.0) '
                  + 'Gecko/20100101 Firefox/39.0')])
    browser.load("https://community.kde.org/Akademy/2015/Monday", )

    events = []
    for day in DAYS:
        #  Events in all tables for which we want to show only one entry
        COMMON = {'BoF wrap-up session in auditorium': False}
        html = browser.download("https://community.kde.org/Akademy/2015/"
                                + day)
        soup = BeautifulSoup(html)
        tables = soup.select('table.wikitable')
        dayEvents = []
        for table in tables:
            rows = table.select('tr')
            location = None
            lastEvent = None
            for row in rows:
                for cell in row.select('th'):
                    if not location:
                        location = cell.text.strip()
                time = None
                what = None
                comments = None
                for cell in row.select('td'):
                    if not time:
                        time = cell.text.strip()
                    elif not what:
                        what = cell.text.strip()
                    elif not comments:
                        comments = cell.text.strip()

                if time and what:
                    if lastEvent and what == lastEvent.subject:
                        lastEvent.duration += 1
                    else:
                        h, m = map(int, time.split(':'))
                        newStartTime = datetime.datetime.combine(currentDate,
                                                                  datetime.time(h, m))
                        e = WikiEvent(
                            newStartTime,
                            location,
                            what,
                            comments)

                        if lastEvent:
                            lastEvent.endDateTime = newStartTime

                        if what in SKIP:
                            lastEvent = False
                            continue

                        if what in COMMON:
                            if COMMON[what]:
                                continue
                            else:
                                location = 'Auditorium'
                                COMMON[what] = True

                        dayEvents.append(e)
                        lastEvent = e
        currentDate += datetime.timedelta(days=1)
        if (day != 'Friday' and len(dayEvents) < 1):
            print(day, 'had no events, this souldnt happen, preemptive leave!')
            exit()
        events.extend(dayEvents)
    return events


def areEqual(wikiEvent, gcalEvent):
    return (wikiEvent.subject == gcalEvent['summary']
            and gcalEvent['start']['dateTime'] == wikiEvent.startTimeStr()
            and gcalEvent['end']['dateTime'] == wikiEvent.endTimeStr()
            and gcalEvent['location'] == wikiEvent.location)


def moved(wikiEvent, gcalEvent):
    return wikiEvent.subject == gcalEvent['summary']


def match(wikiEvents, gcalEvents):
    matches = {'moved': [], 'created': [], 'removed': [], 'stayed': []}
    matchedEvents = []

    # find matches
    for wikiEvent in wikiEvents:
        for gcalEvent in gcalEvents:
            if areEqual(wikiEvent, gcalEvent):
                matches['stayed'].append((wikiEvent, gcalEvent))
                gcalEvents.remove(gcalEvent)
                matchedEvents.append(wikiEvent)
                break

    # find moved events
    for wikiEvent in [e for e in wikiEvents if e not in matchedEvents]:
        for gcalEvent in gcalEvents:
            if moved(wikiEvent, gcalEvent):
                matches['moved'].append((wikiEvent, gcalEvent))
                gcalEvents.remove(gcalEvent)
                matchedEvents.append(wikiEvent)
                break

    # if it didnt move and it didnt match, then it's a new event
    for wikiEvent in [e for e in wikiEvents if e not in matchedEvents]:
        matches['created'].append(wikiEvent)

    # The remaining gcalEvents are no logner in the wiki
    # Queue them to be removed from gcal
    matches['removed'].extend(gcalEvents)
    return matches


def printUsage():
    print(APPLICATION_NAME)
    print()
    print('Usage: sys.argv[0] --calendarId <calendarId>')
    print()
    print('You can get the calendar Id from the iCal URL '
          + 'of your google calendar')
    print('it looks like '
          + '"qkvodipqv8d2mp09uc80a05b0c@group.calendar.google.com"')


def main():

    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('calendar', 'v3', http=http)

    print('Obtaining google calendar events...', end='')
    sys.stdout.flush()
    gcalEvents = getGCalEvents(service)
    print('\tOK')

    print('Obtaining wiki events...', end='')
    wikiEvents = getWikiEvents()
    sys.stdout.flush()
    print('\tOK')

    print(len(wikiEvents), 'events in the wiki')
    print(len(gcalEvents), 'events in gcal')

    print('Matching events...', end='')
    sys.stdout.flush()
    matches = match(wikiEvents, gcalEvents)
    print('\tOK')

    print(len(matches['stayed']), 'events stayed the same')
    print(len(matches['moved']), 'events moved')
    for w, g in matches['moved']:
        print('\tWiki:', w.startTimeStr(), w.subject)
        print('\tGcal:', g['start']['dateTime'], g['summary'])
        print
        g['start']['dateTime'] = w.startTimeStr()
        g['end']['dateTime'] = w.endTimeStr()
        g['location'] = w.location
        service.events().update(calendarId=flags.calendarId,
                                eventId=g['id'],
                                body=g).execute()

    print(len(matches['created']), 'events created')
    for w in matches['created']:
        print('\tWiki:', w.startTimeStr(), w.subject)
        newEvent = {
            'summary': w.subject,
            'description': w.comments,
            'location': w.location,
            'start': {'dateTime': w.startTimeStr()},
            'end': {'dateTime': w.endTimeStr()},
        }
        service.events().insert(calendarId=flags.calendarId,
                                body=newEvent).execute()
    print(len(matches['removed']), 'events removed')
    for g in matches['removed']:
        print('\tGcal:', g['start']['dateTime'], g['summary'])
        service.events().delete(calendarId=flags.calendarId,
                                eventId=g['id']).execute()

if __name__ == "__main__":
    main()
