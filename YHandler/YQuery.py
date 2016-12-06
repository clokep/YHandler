from __future__ import absolute_import

from collections import OrderedDict
import requests
import re
import pkgutil
import json
from urllib import quote_plus

from YHandler.Selectors.DefaultSelector import DefaultSelector
import YHandler


class BaseYahooResource(object):
    def __init__(self, **kwargs):
        # Copy all the parameters into this class.
        self.__dict__.update(kwargs)


class YahooLeagueResource(BaseYahooResource):
    """
    Represents a particular league under the Yahoo Fantasy Sports API.

    """
    def __init__(self, ygame, **kwargs):
        self.ygame = ygame

        # Copy a couple of parameters.
        kwargs['id'] = kwargs['league_id']
        kwargs['is_finished'] = bool(kwargs.get('is_finished', False))

        super(YahooLeagueResource, self).__init__(**kwargs)


class YahooGameResource(object):
    """
    Represents a particular sport and fantasy game (e.g. NFL - season long).

    All queries occur for the current user underneath a game context, and not a
    specific player or team game.

    """
    def __init__(self, yhandler, game_key):
        """
        Constructor creates a YQuery object with a particular fantasy game context, and maps that
        games stats into the stat_categories dictionary
        :param: yhandler - YHandler object
        :param: game_key - Yahoo fantasy API game key - these signify fantasy games, not sport games
        :param: [optional, BaseSelector] selector - selector to use for the querying the xml
        """
        self.yhandler = yhandler
        self.game_key = game_key

        self.stat_categories = {}
        self._map_stat_categories()

    def _map_stat_categories(self):
        """
        Maps a games stat categories to a Python dictionary. If successful,
        the mapping will be held under the stat_categories data attribute.
        :returns: bool - true if the mapping is succesful, false otherwise
        """
        data = self.yhandler.api_req(str.format('game/{0}/stat_categories', self.game_key))

        # Parse the results of the stats
        stats = data['game'][1]['stat_categories']['stats']
        for stat in stats:
            stat = stat['stat']

            # If a stat is for specific positions, parse that data.
            if 'position_types' in stat:
                position_types  = [
                    pos_type['position_type'] for pos_type in stat['position_types']
                ]
            else:
                position_types = []

            # TODO Save the rest of the data from this.
            self.stat_categories[stat['stat_id']] = {
                'name': stat['display_name'],
                'detail': stat['name'],
                'position_type': position_types,
            }

    def get_games_info(self, available_only=False):
        """
        Get game information from Yahoo. This is only the fantasy games
        a particular user is involved in. Not the games of their league.
        :param: available_only - only returns available games for the user
        :returns: selector of games xml for the current user
        """
        if available_only:
            resp = self.yhandler.api_req('games;is_available=1')
        else:
            resp = self.yhandler.api_req('games')
        if resp.status_code != requests.codes['ok']:
            return None

        games = []
        for game in self.selector.iter_select('.//yh:game', self.ns):
            game_detail = {
                'key': game.select_one('./yh:game_key', self.ns).text,
                'code': game.select_one('./yh:code', self.ns).text,
                'name': game.select_one('./yh:name', self.ns).text,
                'season': game.select_one('./yh:season', self.ns).text,
                'type': game.select_one('./yh:season', self.ns).text
            }
            games.append(game_detail)
        return games

    def _unwrap_array(self, data):
        """
        Unwrap the arrays that are wrapped into an object that the Yahoo Fantasy
        API returns. The data will look something like:

        .. code-block:: json

            data = {
                'count': 2,
                '0': { ... },
                '1': { ... },
            }

        """
        return [data[str(i)] for i in range(data['count'])]

    def get_user_leagues(self, active_only=False):
        """
        Get the leagues a user has played in.
        :returns: list - Dictionary of league name/id pairs, None if fail
        """
        data = self.yhandler.api_req(str.format('users;use_login=1/games;game_key={0}/leagues', self.game_key))

        leagues = []

        # This has multiple layers to parse through, generally: users, games,
        # leagues.
        for user in self._unwrap_array(data['users']):
            for game in self._unwrap_array(user['user'][1]['games']):
                for league in self._unwrap_array(game['game'][1]['leagues']):
                    league = YahooLeagueResource(self, **league['league'][0])

                    # If the league is done, potentially skip it.
                    if active_only and league.is_finished:
                        continue

                    leagues.append(league)

        return leagues

    def query_player(self, player_id, resource):
        """
        Query a player resource for a particular fantasy game.
        :param: player_id - Yahoo player id
        :param: resource - Yahoo player resource to query
        :returns: selector around response content, None if fail
        """
        save_format = self.yhandler.format
        self.yhandler.format = self.query_format
        resp = self.yhandler.api_req(str.format('player/{0}.p.{1}/{2}',
                                                self.game_key, player_id, resource))
        self.yhandler.format = save_format
        if resp.status_code != requests.codes['ok']:
            return None
        return self.selector.parse(resp.content)

    def get_player_stats(self, player_stats):
        """
        Get dictionary of player stats
        :param: player_stats - selector around stats xml response
        :returns: stats as a dictionary
        """
        stats = {}
        for stat in player_stats.iter_select('.//yh:player_stats/yh:stats/yh:stat', self.ns):
            stat_id = stat.select_one('./yh:stat_id', self.ns).text
            stat_detail = self.stat_categories[stat_id].copy()
            stat_detail.pop('position_type', None)
            stat_detail['value'] = stat.select_one('./yh:value', self.ns).text
            stat_map = {stat_id: stat_detail}
            stats.update(stat_map)
        return stats

    def get_player_season_stats(self, player_id):
        resp = self.query_player(player_id, "stats")
        if not resp:
            return None
        return self.get_player_stats(resp)

    def get_player_week_stats(self, player_id, week):
        resp = self.query_player(player_id, "stats;type=week;week=" + week)
        if not resp:
            return None
        return self.get_player_stats(resp)

    def find_player(self, league_id, player_name):
        save_format = self.yhandler.format
        self.yhandler.format = self.query_format
        resp = self.yhandler.api_req(str.format('leagues;league_keys={0}.l.{1}/players;search={2}',
                                     self.game_key, league_id, quote_plus(player_name)))
        self.yhandler.format = save_format
        if not resp:
            return None
        sel = self.selector.parse(resp.content)
        players = []
        for player in sel.iter_select('.//yh:players/yh:player', self.ns):
            player_detail = {}
            player_detail['id'] = player.select_one('./yh:player_id', self.ns).text
            player_detail['name'] = player.select_one('./yh:name/yh:full', self.ns).text
            player_detail['team'] = player.select_one('./yh:editorial_team_full_name', self.ns).text
            players.append(player_detail)
        return players

    def query_league(self, league_id, resource):
        """
        Query a league resource for a particular fantasy game.
        :param: league_id - Yahoo league id
        :param: resource - Yahoo league resource to query
        :returns: selector of response content, None if fail
        """
        save_format = self.yhandler.format
        self.yhandler.format = self.query_format
        resp = self.yhandler.api_req(str.format('league/{0}.l.{1}/{2}', self.game_key, league_id, resource))
        self.yhandler.format = save_format
        if resp.status_code != requests.codes['ok']:
            return None
        return self.selector.parse(resp.content)
