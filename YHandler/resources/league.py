from urllib import quote_plus

from YHandler.resources.base import BaseYahooResource, YahooApiData


class YahooManagerResource(BaseYahooResource):
    @property
    def is_current_login(self):
        """Whether this manager is associated with the current API key in use."""
        return bool(self._api_dict.get('is_current_login', False))


class YahooPlayerResource(BaseYahooResource):
    """
    A Yahoo Fantasy Sports player.

    **elgible_positions**
    has_player_notes
    selected_position
        coverage_type
        date
        position
    starting_status
        coverage_type
        date
        is_starting
    is_undroppable
    position_type
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
    def has_player_notes(self):
        return self._api_dict.get('has_player_notes', None)

    @property
    def has_recent_player_notes(self):
        return self._api_dict.get('has_recent_player_notes', None)

    @property
    def status(self):
        """A :class:`str` of the players status, possible values are :const:`'IR'`, :const:`'O'`, :const:`'DL'`. :const:`None` if there's no status available."""
        return self._api_dict.get('status', None)

    @property
    def is_undroppable(self):
        """:const:`False` if the player cannot be dropped. :const:`True` if the player can be dropped."""
        return bool(self._api_dict['is_undroppable'])

    @property
    def on_disabled_list(self):
        """
        :const:`True` if the player is on the disabled list.

        Note that this only includes players that is listed as IR or DL. It does
        not include DTD, O, etc.
        """
        return bool(self._api_dict.get('on_disabled_list', False))


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
            YahooManagerResource(m['manager'], self) for m in api_dict['managers']]

        super(YahooTeamResource, self).__init__(api_dict, *args, **kwargs)

    def api_req(self, sub_resouce, *args, **kwargs):
        """Request a sub-resource of a team."""
        return self._api.api_req(
            'team/{0}/{1}'.format(self.team_key, sub_resouce), *args, **kwargs)

    @property
    def is_current_login(self):
        """Whether this team is associated with the current API key in use."""
        return any([m.is_current_login for m in self.managers])

    def get_roster(self, week=None, date=None):
        """
        Get the roster for this team on a particular week, for the NFL, or date,
        for MLB/NHL/NBA. Defaults to the current week/date if not given.
        """
        # TODO week is a number from X to Y or the key 'current'.
        # TODO Accept dates for NHL/MLB/NBA.
        resource = 'roster'
        if week:
            resource += ';week=' + week
        elif date:
            resource += ';date=' + date.strftime('%Y-%m-%d')
        data = self.api_req(resource)
        return YahooRosterResource(data['team'][1]['roster'], self)


class YahooLeagueRosterPosition(YahooApiData):
    """
    **count**
    **position**
    **position_type** (optional)
        E.g. ``'G'`` or ``'P'``

    """
    @property
    def count(self):
        """An :class:`int`, the number of times this position appears on the roster."""
        # This is sometimes a string, but should never be.
        return int(self._api_dict['count'])


class YahooLeagueStatCategory(YahooApiData):
    def __init__(self, api_dict):
        api_dict['stat_position_types'] = self._flatten_array(
            self._flatten_array(
                api_dict['stat_position_types'], 'stat_position_type'), 'position_type')

        super(YahooLeagueStatCategory, self).__init__(api_dict)


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

    def get_settings(self):
        data = self.api_req('settings')
        settings = data['league'][1]['settings'][0]

        settings['roster_positions'] = [YahooLeagueRosterPosition(p) for p in
            self._flatten_array(settings['roster_positions'], 'roster_position')]

        settings['stat_categories'] = [YahooLeagueStatCategory(c) for c in
            self._flatten_array(settings['stat_categories']['stats'], 'stat')]

        # TODO A lot of the settings are ints cast to string, parse those.
        self._api_dict.update(settings)

    def get_standings(self):
        data = self.api_req('standings')
        teams = self._unwrap_array(data['league'][1]['standings'][0]['teams'])
        for team in teams:
            # The normal team data.
            team = self._unwrap_dict(team['team'][0])
            # Enrich this with the stats information.
            team['team_stats'] = team['team'][1]['team_stats']
            print(team)
