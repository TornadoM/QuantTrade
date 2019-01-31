from data_download import DataReader
from datetime import datetime
from hyperopt import fmin, tpe, hp, STATUS_OK, Trials
import numpy as np
config_params = {
    'INITIAL': 10000,
    'FEE': 0.002,
    'SYMBOL': 'tBTCUSD',
    'SECTION': 'hist',
    'START': '2018-07-01 00:00:00',
    'END': '2019-01-01 00:00:00',
    'TIMEFRAME': '1h',
    'MAX_NUM_REFS': 300,
    'K1': 0.56,
    'K2': 0.58,
    'NUM_REFS': 11
}

hyperopt_params = {
    'K1': hp.quniform('K1', 0.1, 2.0, 0.02),
    'K2': hp.quniform('K2', 0.1, 2.0, 0.02),
    'NUM_REFS': hp.choice('NUM_REFS', np.arange(10, 300, dtype=int))
}


class Quant_Trader():

    def __init__(self, config_params):
        self.Config = config_params.copy()

        self.path_params = {'TimeFrame': self.Config['TIMEFRAME'],
                            'Symbol': self.Config['SYMBOL'],
                            'Section': self.Config['SECTION']}

        self.query_params = {'limit': 5000,
                             'start': self.Config['START'],
                             'end': self.Config['END'],
                             'sort': 1}

        self.datetime_pattern = '%Y-%m-%d %H:%M:%S'

        self.prev_data_frag = self.data = self.response_format = None

        self.usd_balance = self.Config['INITIAL']
        self.btc_balance = 0

    def _data_reader_init(self):
        self.query_params['start'] = round(datetime.strptime(self.query_params['start'],
                                                                 self.datetime_pattern).timestamp()*1000)
        self.query_params['end'] = round(datetime.strptime(self.query_params['end'],
                                                               self.datetime_pattern).timestamp()*1000)
        data_reader = DataReader(self.path_params, self.query_params, self.Config['MAX_NUM_REFS'])
        self.all_data, self.response_format = data_reader.get_data()


    def _data_split(self, num_refs=None):
        if num_refs is None:
            num_refs = self.Config['NUM_REFS']
        self.prev_data_frag = self.all_data[self.Config['MAX_NUM_REFS']-num_refs:self.Config['MAX_NUM_REFS']]
        self.data = self.all_data[self.Config['MAX_NUM_REFS']:]


    def _calc_benchmark(self):
        # Get Highest-High, Lowest-Low, Highest-Close and Lowest-Close from Transactions
        tmp_high = tmp_low = tmp_high_close = tmp_low_close = None
        for candle in self.prev_data_frag:
            high_val = candle[self.response_format.index('High')]
            low_val = candle[self.response_format.index('Low')]
            close_val = candle[self.response_format.index('Close')]

            tmp_high = high_val if (not tmp_high) or (high_val > tmp_high) else tmp_high
            tmp_low = low_val if (not tmp_low) or (low_val < tmp_low) else tmp_low
            tmp_low_close = close_val if (not tmp_low_close) or (close_val < tmp_low_close) else tmp_low_close
            tmp_high_close = close_val if (not tmp_high_close) or (close_val > tmp_high_close) else tmp_high_close

        max_range = max(float(tmp_high)-float(tmp_low_close), float(tmp_high_close)-float(tmp_low))

        return max_range

    def _sell(self, price):
        self.usd_balance += self.btc_balance * price * (1 - self.Config['FEE'])
        self.btc_balance = 0

    def _buy(self, price):
        self.btc_balance += self.usd_balance * (1 - self.Config['FEE']) /price
        self.usd_balance = 0

    def _trade(self, k1=None, k2=None):
        if k1 is None:
            k1 = self.Config['K1']
        if k2 is None:
            k2 = self.Config['K2']

        for candle in self.data:
            open_val = candle[self.response_format.index('Open')]
            high_val = candle[self.response_format.index('High')]
            low_val = candle[self.response_format.index('Low')]

            max_range = self._calc_benchmark()
            buy_price = open_val + k1*max_range
            sell_price = open_val - k2*max_range
            self.prev_data_frag.pop(0)
            self.prev_data_frag.append(candle)

            if self.usd_balance:
                if low_val <= buy_price <= high_val:
                    self._buy(buy_price)
                    continue
            else:
                if low_val <= sell_price <= high_val:
                    self._sell(sell_price)
                    continue

        if self.btc_balance:
            self.usd_balance += self.btc_balance * candle[self.response_format.index('Close')]

    def _search(self, hyperopt_params):
        k1 = hyperopt_params['K1']
        k2 = hyperopt_params['K2']
        num_refs = hyperopt_params['NUM_REFS']
        self.usd_balance = self.Config['INITIAL']
        self.btc_balance = 0
        # output the current set of hyper-parameter values
        print("\n-----------\n")
        print("parameters to try out")
        print(hyperopt_params)
        print("\n")

        self._data_split(num_refs)
        self._trade(k1, k2)
        final_balance, win_rate, market_rate, relative_rate = self.get_metrics()
        print("win rate on current set of hyper-parameter values = %s\n" % win_rate)
        win_rate = float(win_rate[:-1])

        if win_rate > self.best_win_rate:
            self.best_win_rate = win_rate
        print("best win rate so far = %s %%" % self.best_win_rate)

        return {"loss": -win_rate, "status": STATUS_OK}

    def run(self):
        self._data_reader_init()
        self._data_split()
        self._trade()

    def run_with_hyperopt(self, hyperopt_params):
        self._data_reader_init()
        self.best_win_rate = -float('inf')
        best = fmin(self._search, hyperopt_params, algo=tpe.suggest, max_evals=100)
        best['NUM_REFS'] = np.arange(10, 300, dtype=int)[best['NUM_REFS']]
        print("\n-----------\n")
        print("best hyper-parameters:")
        print(best)
        print("\n")
        print("")
        return best

    def get_metrics(self):
        win_rate = round((self.usd_balance / self.Config['INITIAL'] - 1) * 100, 2)
        final_close = self.data[-1][self.response_format.index('Close')]
        first_open = self.data[0][self.response_format.index('Open')]
        market_rate = round((final_close / first_open - 1) * 100, 2)
        relative_rate = win_rate - market_rate
        return self.usd_balance, str(win_rate)+'%', str(market_rate)+'%', str(relative_rate)+'%'

if __name__ == '__main__':

    quant_trader = Quant_Trader(config_params)
    hyperopt_flag = input('Wanna Hyper-Parameter Optimization?\n(y/n)')
    if hyperopt_flag == 'y':
        best = quant_trader.run_with_hyperopt(hyperopt_params)
        config_params.update(best)
        quant_trader = Quant_Trader(config_params)
        quant_trader.run()
        final_balance, win_rate, market_rate, relative_rate = quant_trader.get_metrics()
        print("\n-----------\n")
        print("Final USD Balance: %s \n" % final_balance)
        print("Absolute Return: %s \n" % win_rate)
        print("Market Return: %s \n" % market_rate)
        print("Relative Return: %s \n" % relative_rate)
    elif hyperopt_flag == 'n':
        quant_trader.run()
        final_balance, win_rate, market_rate, relative_rate = quant_trader.get_metrics()
        print("\n-----------\n")
        print("Final USD Balance: %s \n" % final_balance)
        print("Absolute Return: %s \n" % win_rate)
        print("Market Return: %s \n" % market_rate)
        print("Relative Return: %s \n" % relative_rate)
    else:
        pass

