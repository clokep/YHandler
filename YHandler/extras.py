import datetime
import re

from bs4 import BeautifulSoup

import lxml.etree

import requests


"""
Other methods for retrieving sports related information
from Yahoo's network.
"""

def get_player_id(player_name, sport_code):
    """
    Uses Yahoo's player search to find player IDs according to the search criteria.
    NOTE: This query uses the player search outside of Yahoo's fantasy network, and may
    be unstable for continued use. Use with caution. You may want to also look at the find
    player in the YQuery class. It peforms the search within the fantasy API.
    :param: player_name - player name to search for
    :param: sport_code - sport abbreviation (I think) (e.g. nfl, nba, mlb, nhl)
    :returns: list of player IDs that can be used Yahoo fantasy API to query player resources (info, stats, etc...)
    """
    resp = requests.get(str.format('http://sports.yahoo.com/{0}/players', sport_code),
                        params={ 'type': 'lastname', 'first': '1', 'query': player_name})
    results = []
    if resp.status_code != requests.codes['ok']:
        return results
    selector = lxml.etree.fromstring(resp.content, lxml.etree.HTMLParser())
    player_ids = selector.xpath('//table/tr[contains(td,"Search Results")]/following::tr[position()>1]/td[1]//@href')
    if player_ids:
        for p in player_ids:
            id = re.search(r'\d+', p)
            if id:
                results.append(id.group(0))
    return results


def get_starting_goalies(date=None):
    """
    Get today's starting NHL goalies.

    Returns a :class:`list` of :class:`dict`, each contains the keys:

        ``home_team``
            The :class:`str` name of the home team.
        ``home_goalie``
            A :class:`dict` of the home goalie.
        ``away_team``
            The :class:`str` name of the away team.
        ``away_goalie``
            A :class:`dict` of the away goalie.
        ``date``
            The start of the game as a :class:`datetime`.

        Each goalie is a :class:`dict` with the following keys:

            ``name``
            ``headshot``
            ``likelihood``
                A :class:`dict` with the following keys:

                ``status``
                    A :class:`str` which is ``Confirmed``, ``Likely``, or
                    ``Unconfirmed``.
                ``date`` (optional)
                    The :class:`datetime` the likelihood was last updated.
            ``description``
                ``short``
                ``long`` (optional)
                ``author`` (optional)
                ``author_link`` (optional)

    """

    # Get the matchups for a particular date
    if not date:
        date = datetime.date.today()

    url = 'http://www2.dailyfaceoff.com/starting-goalies/{0}/{1}/{2}/'.format(date.year, date.month, date.day)

    response = requests.get(url)

    # Parse the HTML.
    soup = BeautifulSoup(response.text, 'html.parser')

    # The result.
    matchups = []

    # Ignore the rest of the page except the "matchups" div.
    matchups_element = soup.find(id="matchups")

    # Iterate through children.
    current_matchup = {}
    for element in matchups_element.children:
        if element.name == 'h4':
            if current_matchup:
                matchups.append(current_matchup)
                current_matchup = {}

            current_matchup['home_team'], current_matchup['away_team'] = element.string.split(' at ')

        if element.name == 'div':
            if element.attrs['class'] == ['goalie', 'away']:
                current_matchup['away_goalie'] = _parse_goalie(element)
            elif element.attrs['class'] == ['goalie', 'home']:
                current_matchup['home_goalie'] = _parse_goalie(element)
            elif element.attrs['class'] == ['date']:
                current_matchup['date'] = _parse_date(element.string)

    # Handle the hanging matchup at the end.
    matchups.append(current_matchup)

    return matchups


def _parse_date(date_str):
    """
    Parse the date string to a datetime object, the input is expected to look
    like:

    * ``'Dec. 8, 2016, 1:47 p.m.'``
    * ``'Dec. 9, 2016 8:30 p.m.'``
    * ``'Dec. 9, 2016 7 p.m.'``
    * ``'Jan. 31, 2017, noon'``

    """
    date_str = date_str.replace('.m.', 'm')

    # The word 'noon' is sometimes used in dates.
    date_str = date_str.replace('noon', '12 pm')

    # Minutes are only given if they're applicable. Handle this in the pattern.
    minutes = ':%M' if ':' in date_str else ''
    format_strs = ['%b. %d, %Y{0} %I{1} %p'.format(comma, minutes) for comma in [',', '']]

    # Parse to a datetime object, two formats are supported so try both.
    for format_str in format_strs:
        try:
            return datetime.datetime.strptime(date_str, format_str)
        except ValueError:
            continue

    raise ValueError("Unable to parse date: %s" % date_str)

def _parse_goalie(goalie_element):
    """Parse a home/away goalie element. Returns the expected starting goalie and confidence."""
    data = {}

    # Get the goalie's name.
    try:
        data['name'] = goalie_element.h5.a.string
    except AttributeError:
        # For goalies which aren't confirmed, the content is written out via
        # JavaScript. Split out the HTML from inside the document.write call.
        html_string = goalie_element.script.string.split('"', 1)[1]
        html_string = html_string.rsplit('"', 1)[0]

        # Note that we need to add back the goalie element.
        html_string = '<div>' + html_string.replace('\\"', '"') + '</div>'
        return _parse_goalie(BeautifulSoup(html_string, 'html.parser'))

    # Get the rest of the information.
    data['headshot'] = goalie_element.find('img', class_='headshot').attrs['src']
    dts = goalie_element.find_all('dt')
    data['likelihood'] = {'status': dts[0].string}
    # Sometimes there's no date data available.
    try:
        data['likelihood']['date'] = _parse_date(dts[1].string)
    except IndexError:
        pass

    # Pull out the brief descriptions of where the information is from.
    ps = goalie_element.find_all('p')
    data['description'] = {'short': ps[0].string.strip()}
    try:
        data['description']['long'] = ps[1].string.strip()
        data['description']['author'] = ps[2].a.string.strip()
        data['description']['author_link'] = ps[2].a.attrs['href']
    except IndexError:
        pass

    return data
