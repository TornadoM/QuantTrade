import requests
from datetime import datetime
import time
class DataReader():

    def __init__(self, path_params, query_params, num_refs):
        self.api = 'https://api.bitfinex.com/v2/candles/trade'
        self.response_format = ['MilliTimeStamp', 'Open', 'Close', 'High', 'Low', 'Volume']

        self.path_params = path_params
        self.query_params = query_params

        self.datetime_pattern = '%Y-%m-%d %H:%M:%S'

        self.start_ts = self.query_params['start']
        self.end_ts = self.query_params['end']
        self.num_refs = num_refs

        time_interval_map = {'m': 60000, 'h': 3600000}
        self.time_interval = int(self.path_params['TimeFrame'][:-1]) * \
                             time_interval_map[self.path_params['TimeFrame'][-1]]

        self._generate_link()

    def _generate_link(self):
        self.link = self.api + ':' + self.path_params['TimeFrame'] + \
                    ':' + self.path_params['Symbol'] + \
                    '/' + self.path_params['Section']

    def _data_request(self):
        responses_all = []
        self.start_ts = self.start_ts - (self.num_refs * self.time_interval)
        self.query_params['start'] = self.start_ts
        self.end_ts = self.end_ts - self.time_interval
        self.query_params['end'] = self.end_ts
        while True:
            tmp_response = requests.get(self.link, params=self.query_params).json()
            if tmp_response[-1] == 'ratelimit: error':
                time.sleep(5)
                continue
            responses_all += tmp_response
            if len(tmp_response) < 5000:
                break
            else:
                self.start_ts = tmp_response[-1][0] + self.time_interval
                if self.start_ts < self.end_ts:
                    self.query_params['start'] = self.start_ts
                    continue
                else:
                    break
        return responses_all

    def get_data(self):
        response = self._data_request()
        return response, self.response_format
