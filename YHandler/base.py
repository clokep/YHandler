from os.path import splitext
from urlparse import parse_qs, urljoin
import webbrowser

import requests

from YHandler.OAuth1Lite import OAuth1Lite
from YHandler.AuthManager import CSVAuthManager, JsonAuthManager
from YHandler.resources import YahooGameResource

GET_TOKEN_URL = 'https://api.login.yahoo.com/oauth/v2/get_token'
AUTHORIZATION_URL = 'https://api.login.yahoo.com/oauth/v2/request_auth'
REQUEST_TOKEN_URL = 'https://api.login.yahoo.com/oauth/v2/get_request_token'
CALLBACK_URL = 'oob'


class YahooApiException(Exception):
    pass


class YahooFantasySports:
    _base_url = 'https://fantasysports.yahooapis.com/fantasy/v2/'
    _format = 'json'

    def __init__(self, authf='auth.json'):
        ext = splitext(authf)[-1].lower()
        if ext == '.csv':
            self.authc = CSVAuthManager(authf)
        elif ext == '.json':
            self.authc = JsonAuthManager(authf)
        else:
            self.authc = CSVAuthManager(authf)
        self.authd = self.authc.get_authvals()

    def reg_user(self):
        """
        step #1: Signup and get token https://developer.yahoo.com/oauth/guide/oauth-auth-flow.html
        step #2: Get a request token https://developer.yahoo.com/oauth/guide/oauth-requesttoken.html
        step #3: Get user authorization https://developer.yahoo.com/oauth/guide/oauth-userauth.html
        step #4: Get access token https://developer.yahoo.com/oauth/guide/oauth-accesstoken.html
        """
        # step #1: Signup and get token https://developer.yahoo.com/oauth/guide/oauth-auth-flow.html
        # step #2: Get a request token https://developer.yahoo.com/oauth/guide/oauth-requesttoken.html
        oauth_request = OAuth1Lite(self.authd['consumer_key'], self.authd['consumer_secret'], callback=CALLBACK_URL)
        response = requests.post(REQUEST_TOKEN_URL, auth=oauth_request)
        if response.status_code != requests.codes['ok']:
            return response
        qs = parse_qs(response.text)
        self.authd['oauth_token'] = (qs['oauth_token'][0])
        self.authd['oauth_token_secret'] = (qs['oauth_token_secret'][0])

        # step #3: Get user authorization https://developer.yahoo.com/oauth/guide/oauth-userauth.html
        print "You will now be directed to a website for authorization.\n\
               Please authorize the app, and then copy and paste the provided PIN below."
        webbrowser.open("%s?oauth_token=%s" % (AUTHORIZATION_URL, self.authd['oauth_token']))
        self.authd['oauth_verifier'] = raw_input('Please enter your PIN:')

        # step #4: Get access token https://developer.yahoo.com/oauth/guide/oauth-accesstoken.html
        return self.get_login_token()

    def get_login_token(self):
        """
        step #4: Get access token https://developer.yahoo.com/oauth/guide/oauth-accesstoken.html
        """
        oauth_access = OAuth1Lite(self.authd['consumer_key'], self.authd['consumer_secret'],
                                  self.authd['oauth_token'], self.authd['oauth_token_secret'])
        oauth_access.add_param('oauth_verifier', self.authd['oauth_verifier'])
        response = requests.post(GET_TOKEN_URL, auth=oauth_access)
        if response.status_code != requests.codes['ok']:
            return response
        qs = parse_qs(response.content)
        self.authd['oauth_access_token'] = qs['oauth_token'][0]
        self.authd['oauth_access_token_secret'] = qs['oauth_token_secret'][0]
        self.authd['oauth_session_handle'] = qs['oauth_session_handle'][0]
        if self.authc:
            self.authc.write_authvals(self.authd)
        return response

    def refresh_token(self):
        """
        step #5: Refresh the access token https://developer.yahoo.com/oauth/guide/oauth-refreshaccesstoken.html

        This is the method that you should always call after you've gone through the registration process - steps
        1 thru 4. Essentially, you should never have to re-register with Yahoo, and can always reuse credentials
        by refreshing your tokens.
        """
        oauth_refresh = OAuth1Lite(self.authd['consumer_key'], self.authd['consumer_secret'],
                                   self.authd['oauth_access_token'], self.authd['oauth_access_token_secret'])
        oauth_refresh.add_param('oauth_session_handle', self.authd['oauth_session_handle'])
        response = requests.post(GET_TOKEN_URL, auth=oauth_refresh)
        if response.status_code != requests.codes['ok']:
            return response
        qs = parse_qs(response.content)
        self.authd['oauth_access_token'] = qs['oauth_token'][0]
        self.authd['oauth_access_token_secret'] = qs['oauth_token_secret'][0]
        self.authd['oauth_session_handle'] = qs['oauth_session_handle'][0]
        if self.authc:
            self.authc.write_authvals(self.authd)
        return response

    def _call_api(self, url, req_meth, data, headers):
        """
        Makes an the request to the yahoo api using oauth credentials
        :param: url - request url
        :param: req_meth - request method to used
        :param: data - additional fields to send with the request
        :param: headers - additional headers to send with the request
        :returns Response object
        """
        oauth_api = OAuth1Lite(self.authd['consumer_key'],
                               self.authd['consumer_secret'],
                               self.authd['oauth_access_token'],
                               self.authd['oauth_access_token_secret'])
        return requests.request(method=req_meth, url=url,
                                data=data, headers=headers,
                                auth=oauth_api,
                                params={'format': self._format})

    def api_req(self, querystring, req_meth='GET', data={}, headers={}):
        """
        Sends the specified querysting to the yahoo fantasy api and returns
        the response. This should be used after authorization is complete.
        :param: querystring - query string to send
        :param: req_meth - request method to used
        :param: data - additional fields to send with the request
        :param: headers - additional headers to send with the request
        :returns Response object
        """
        # Enforce authentication has happened.
        if ('oauth_access_token' not in self.authd) or ('oauth_access_token_secret' not in self.authd) or (not (self.authd['oauth_access_token'] and self.authd['oauth_access_token_secret'])):
            self.reg_user()

        url = urljoin(self._base_url, querystring)
        response = self._call_api(url, req_meth, data=data, headers=headers)

        # Both authtokens exist, but the request was rejected. Assume the token
        # expired, request a new one and try again.
        # TODO This could be a LOT more robust.
        if response.status_code != requests.codes['ok']:
            self.refresh_token()
            response = self._call_api(url, req_meth, data=data, headers=headers)

        # If the response code is still not OK, then nothing we can do.
        if response.status_code != requests.codes['ok']:
            # Try to get a good error message.
            try:
                message = response.json()['error']['description']
            except (ValueError, KeyError):
                message = response.content

            raise YahooApiException(
                '{0}: {1}'.format(response.status_code, message))

        # The response is in JSON, but always encapsulated at a top-level
        # 'fantasy_content' element.
        return response.json()['fantasy_content']

    def get_game(self, game_key):
        data = self.api_req('game/' + game_key)
        game = data['game'][0]

        return YahooGameResource(game, parent=self)

    def get_games(self, available_only=False):
        """
        Get game information from Yahoo. This is only the fantasy games
        a particular user is involved in. Not the games of their league.
        :param: available_only - only returns available games for the user
        :returns: selector of games xml for the current user
        """
        query = 'games'
        if available_only:
            query = 'games;is_available=1'
        resp = self._api.api_req(query)

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
