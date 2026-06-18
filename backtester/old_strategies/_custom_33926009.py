class Test:
    def on_data(self,df):
        df['signal']=0
        return df