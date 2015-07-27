# akademy-bof-gcal-synchronizer
Akademy 2015 BoF Google Calendar Synchronizer

This script will synchronize the events on the Akademy 2015 Community wiki with a google calendar. It'll try to never delete events when they are modified on the wiki, and instead find and update the corresponding event on google calendar.

## Dependencies
* Spynner
* oauth2client
* BeautifulSoup4

If you want to run on a headless server Spynner will need an X session. You can use xvfb-run for this.

## Usage
Just run

    python syncbofs.py googleCalendarId
  
or

    xvfb-run python syncbofs.py googleCalendarId

if you're using a headless installation

You can get your google calendar Id from the iCal link to your calendar on the google calendar website and it should look something like this:

    qkvodipqv8d2mp09uc80a05b0c@group.calendar.google.com
