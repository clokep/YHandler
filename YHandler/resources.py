from __future__ import absolute_import

from urllib import quote_plus


class YahooApiData(object):
    """Provides the results of an API request as properties on an object."""
    def __init__(self, api_dict):
        self._api_dict = api_dict

    def __getattr__(self, attribute):
        """Proxy access to stored attributes."""
        if attribute not in self._api_dict:
            raise AttributeError(attribute)
        return self._api_dict[attribute]

    def _unwrap_array(self, data):
        """
        Unwrap the arrays that are wrapped into an object that the Yahoo Fantasy
        API returns. The data will look something like:

        .. code-block:: json

            {
                'count': 2,
                '0': { obj1 },
                '1': { obj2 },
            }

        This would return simply:

        .. code-block:: json

            [obj1, obj2]

        """
        return [data[str(i)] for i in range(data['count'])]

    def _flatten_array(self, data, key):
        """
        Flatten an array that has keys that are all identical, e.g.:

        .. code-block:: json

            [
                {'position': 'C'},
                {'position': 'LW'},
            ]

        This would return simply:

        .. code-block:: json

            ['C', 'LW']

        """
        return [item[key] for item in data]

    def _unwrap_dict(self, data):
        """
        Unwrap the dict that is given in array that the Yahoo Fantasy API
        returns. The data will look something like:

        .. code-block:: json

            [
                {'key1': obj1},
                {'key2': obj2},
                []
            ]

        This would return simply:

        .. code-block:: json

            {
                'key1': obj1,
                'key2': obj2,
            }

        """
        result = {}
        for item in data:
            # Some data ends with an empty list, just ignore it.
            if item == []:
                continue

            for key, value in item.iteritems():
                # TODO Ensure we're not overwriting key.
                result[key] = value

        return result


class BaseYahooResource(YahooApiData):
    """
    A "Resource" on the Yahoo Fantasy Sports API. This has data associated with
    it and represents a queryable endpoint.

    """
    def __init__(self, api_dict, parent):
        super(BaseYahooResource, self).__init__(api_dict)
        self._parent = parent

    @property
    def _api(self):
        """Recurse via parents until you find a YHandler instance."""
        # Avoid a recursive import.
        from YHandler.base import YahooFantasySports

        # TODO Better error handling.
        parent = self._parent
        while True:
            if isinstance(parent, YahooFantasySports):
                return parent
            parent = parent._parent


class YahooManagerResource(BaseYahooResource):
    @property
    def is_current_login(self):
        """Whether this manager is associated with the current API key in use."""
        return bool(self._api_dict.get('is_current_login', False))


class YahooPlayerResource(BaseYahooResource):
    """
    A Yahoo Fantasy Sports player.

    **elgible_positions**

    **headshot**

    """

    def __init__(self, api_dict, *args, **kwargs):
        # Convert the internal data.
        _api_dict = {}
        for item in api_dict:
            if isinstance(item, list):
                _api_dict.update(self._unwrap_dict(api_dict[0]))
            elif isinstance(item, dict):
                _api_dict.update(item)

        # Now that the api_dict isn't as crazy, parse more data.
        _api_dict['eligible_positions'] = self._flatten_array(
            _api_dict['eligible_positions'], 'position')
        _api_dict['selected_position'] = self._unwrap_dict(
            _api_dict['selected_position'])

        super(YahooPlayerResource, self).__init__(_api_dict, *args, **kwargs)

    def api_req(self, sub_resouce, *args, **kwargs):
        """Request a sub-resource of a team."""
        return self._api.api_req(
            'player/{0}/{1}'.format(self.player_key, sub_resouce), *args, **kwargs)

    def get_stats(self, week=None):
        resource = 'stats'
        if week:
            resource += ';week=' + week
        data = self.api_req(resource)

        # No need to make a resource here, but clean-up the data.
        stats = data['player'][1]['player_stats']
        result = stats['0']
        result['stats'] = [s['stat'] for s in stats['stats']]

        return result

    @property
    def status(self):
        """A :class:`str` of the players status, possible values are :const:`'IR'`, :const:`'DL'`. :const:`None` if there's no status available."""
        return self._api_dict.get('status', None)

    @property
    def is_undroppable(self):
        """:const:`False` if the player cannot be dropped. :const:`True` if the player can be dropped."""
        return bool(self._api_dict['is_undroppable'])


class YahooRosterResource(BaseYahooResource):
    def __init__(self, api_dict, *args, **kwargs):
        # Convert the players to player resources.
        api_dict['players'] = [
            YahooPlayerResource(p['player'], self) for p in self._unwrap_array(api_dict.pop('0')['players'])]

        super(YahooRosterResource, self).__init__(api_dict, *args, **kwargs)


class YahooTeamResource(BaseYahooResource):
    def __init__(self, api_dict, *args, **kwargs):
        # Convert the manager dict into YahooManagerResource objects.
        api_dict['managers'] = [
            YahooManagerResource(m['manager']) for m in api_dict['managers']]

        super(YahooTeamResource, self).__init__(api_dict, *args, **kwargs)

    def api_req(self, sub_resouce, *args, **kwargs):
        """Request a sub-resource of a team."""
        return self._api.api_req(
            'team/{0}/{1}'.format(self.team_key, sub_resouce), *args, **kwargs)

    @property
    def is_current_login(self):
        """Whether this team is associated with the current API key in use."""
        return any([m.is_current_login for m in self.managers])

    def get_roster(self, week='current'):
        # TODO week is a number from X to Y or the key 'current'.
        # TODO Accept dates for NHL/MLB/NBA.
        data = self.api_req('roster;week=' + week)
        return YahooRosterResource(data['team'][1]['roster'], self)


class YahooLeagueResource(BaseYahooResource):
    """
    Represents a particular league under the Yahoo Fantasy Sports API.

    """
    @property
    def id(self):
        return self.league_id

    @property
    def key(self):
        return self.league_key

    @property
    def is_finished(self):
        return bool(self._api_dict.get('is_finished', False))

    def api_req(self, sub_resouce, *args, **kwargs):
        """Request a sub-resource of a league."""
        return self._api.api_req(
            'league/{0}/{1}'.format(self.league_key, sub_resouce), *args, **kwargs)

    def scoreboard(self):
        """The current matchups for all teams in the league."""
        data = self.api_req('scoreboard')

        matchups = []
        league = data['league'][1]['scoreboard']
        return self._unwrap_array(league['matchups'])

    def get_players(self):
        data = self.api_req('players')

        players = data['league'][1]['players']
        return [
            YahooPlayerResource(p['player'], self) for p in self._unwrap_array(players)]

    def find_player(self, name):
        """
        Search for a player by name.

        Parameters:
            ``name`` (:class:`str`):
                The name (full or partial) to search for a player.

        Returns:
            :class:`list` of :class:`~YHandler.resources.YahooPlayerResource`:
                The players who match the given name.

        """
        data = self.api_req('players;search={0}'.format(quote_plus(name)))

        players = data['league'][1]['players']
        return [
            YahooPlayerResource(p['player'], self) for p in self._unwrap_array(players)]

    def get_teams(self):
        """
        Returns:
            :class:`list` of :class:`~YHandler.resources.YahooTeamResource`

        """
        data = self.api_req('teams')

        teams = []
        for team in self._unwrap_array(data['league'][1]['teams']):
            team = self._unwrap_dict(team['team'][0])
            teams.append(YahooTeamResource(team, self))
        return teams

    def get_team(self):
        """Get the team associated with the current API key."""
        for team in self.get_teams():
            if team.is_current_login:
                return team

        # TODO Raise exception.


class YahooGameStat(YahooApiData):
    """Note that this isn't really a resource, you can't query anything else on it."""
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
        self.stat_categories = {}
        self._map_stat_categories()

    def _map_stat_categories(self):
        """
        Maps a games stat categories to a Python dictionary. If successful,
        the mapping will be held under the stat_categories data attribute.
        :returns: bool - true if the mapping is succesful, false otherwise
        """
        data = self._api.api_req(
            'game/{0}/stat_categories'.format(self.game_key))

        # Parse the results of the stats call.
        stats = data['game'][1]['stat_categories']['stats']
        for stat in stats:
            stat = YahooGameStat(stat['stat'])
            self.stat_categories[stat.stat_id] = stat

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
