from datetime import date, datetime

from YHandler.resources.base import BaseYahooResource, YahooApiData
from YHandler.resources.league import YahooLeagueResource


class YahooGameWeek(YahooApiData):
    """
    **week**
        The :class:`int` week number for this game.
    """
    DATE_FORMAT = '%Y-%m-%d'

    @property
    def start(self):
        return datetime.strptime(self._api_dict['start'], self.DATE_FORMAT).date()

    @property
    def end(self):
        return datetime.strptime(self._api_dict['end'], self.DATE_FORMAT).date()

    @property
    def is_current(self):
        """:const:`True` if this week is the one currently being played, otherwise :const:`False`"""
        return self.start <= date.today() <= self.end


class YahooGameStat(YahooApiData):
    def __init__(self, api_dict):
        # Turn position_types into a list.
        if 'position_types' in api_dict:
            api_dict['position_types'] = self._flatten_array(
                        api_dict['position_types'], 'position_type')
        else:
            api_dict['position_types'] = []

        # Turn base_stats into a list of stat IDs.
        if 'base_stats' in api_dict:
            api_dict['base_stats'] = [int(id) for id in self._flatten_array(
                self._flatten_array(
                    api_dict['base_stats'], 'base_stat'), 'stat_id')]
        else:
            api_dict['base_stats'] = []

        super(YahooGameStat, self).__init__(api_dict)

    @property
    def is_composite_stat(self):
        return bool(self._api_dict.get('is_composite_stat', False))

    @property
    def sort_order(self):
        """:const:`True` if a larger value in this is better. :const:`False` if a smaller value is better."""
        return bool(self._api_dict['sort_order'])


class YahooGamePositionType(YahooApiData):
    """
    **display_name**
        The :class:`str` name of this position type, e.g. ``'Goaltenders'``.

    **type**
        The :class:`str` identifier, e.g. ``'G'``.

    """


class YahooGameRosterPosition(YahooApiData):
    """
    **abbreviation**

    **position**

    **display_name**

    **position_type**

    """
    @property
    def is_bench(self):
        """:const:`True` if this is the bench position (player will not be used), otherwise :const:`False`."""
        return bool(self._api_dict.get('is_bench', False))

    @property
    def is_disabled_list(self):
        """:const:`True` if this position is for players on the disabled list, otherwise :const:`False`."""
        return bool(self._api_dict.get('is_disabled_list', False))


class YahooGameResource(BaseYahooResource):
    """
    Represents a particular sport and fantasy game (e.g. NFL - season long).

    All queries occur for the current user underneath a game context, and not a
    specific player or team game.

    """
    def __init__(self, *args, **kwargs):
        """
        Constructor creates a YQuery object with a particular fantasy game context, and maps that
        games stats into the stat_categories dictionary
        :param: yhandler - YHandler object
        :param: game_key - Yahoo fantasy API game key - these signify fantasy games, not sport games
        :param: [optional, BaseSelector] selector - selector to use for the querying the xml
        """
        super(YahooGameResource, self).__init__(*args, **kwargs)

        # Get additional metadata.
        self.game_weeks = []
        self._get_game_weeks()

        self.stat_categories = {}
        self._get_stat_categories()

        self.position_types = {}
        self._get_position_types()

        self.roster_positions = {}
        self._get_roster_positions()

    def _get_game_weeks(self):
        data = self._api.api_req('game/{0}/game_weeks'.format(self.game_key))

        weeks = self._flatten_array(
            self._unwrap_array(data['game'][1]['game_weeks']), 'game_week')
        self.game_weeks = [YahooGameWeek(w) for w in weeks]

    def _get_stat_categories(self):
        """
        Maps a games stat categories to a Python dictionary. The mapping will be
        held under the stat_categories data attribute.

        """
        data = self._api.api_req('game/{0}/stat_categories'.format(self.game_key))

        # Parse the results of the stats call.
        stats = data['game'][1]['stat_categories']['stats']
        for stat in stats:
            stat = YahooGameStat(stat['stat'])
            self.stat_categories[stat.stat_id] = stat

    def _get_position_types(self):
        data = self._api.api_req('game/{0}/position_types'.format(self.game_key))

        for position_type in data['game'][1]['position_types']:
            position_type = YahooGamePositionType(position_type['position_type'])
            self.position_types[position_type.type] = position_type

    def _get_roster_positions(self):
        data = self._api.api_req('game/{0}/roster_positions'.format(self.game_key))

        for roster_position in data['game'][1]['roster_positions']:
            roster_position = YahooGameRosterPosition(roster_position['roster_position'])
            self.roster_positions[roster_position.position] = roster_position

    def get_leagues(self, active_only=False):
        """
        Get all leagues a user has ever played in.

        Parameters:
            ``active_only`` (:class:`bool`):
                If set to :const:`False` (the default), all leagues the user has
                ever participated in will be returned. Setting this to
                :const:`True` will reduce this to only current leagues.

        Returns:
            :class:`list` of :class:`~YHandler.resources.YahooLeagueResource`:
                Leagues that the current user belongs to.

        """
        data = self._api.api_req(
            'users;use_login=1/games;game_key={0}/leagues'.format(self.game_key))

        leagues = []

        # This has multiple layers to parse through, generally: users, games,
        # leagues.
        for user in self._unwrap_array(data['users']):
            for game in self._unwrap_array(user['user'][1]['games']):
                for league in self._unwrap_array(game['game'][1]['leagues']):
                    league = YahooLeagueResource(league['league'][0], self)

                    # If the league is done, potentially skip it.
                    if active_only and league.is_finished:
                        continue

                    leagues.append(league)

        return leagues
