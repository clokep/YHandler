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
