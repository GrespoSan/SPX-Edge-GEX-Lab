"""Aligned chart coordinates and immutable SPX exposures; no provider requests."""
import copy

import numpy as np
import pandas as pd
import pytest

from edge_charts import candles_gex_figure


def inputs():
    result={'symbol':'SPX','spot':6000.,'call_wall':6020.,'put_wall':5980.,'flip':6005.,
            'rows':pd.DataFrame({'strike':[5980.,6000.,6020.],'call_gex':[1e9,2e9,3e9],
                                 'put_gex':[-2e9,-1e9,-.5e9],'net_gex':[-1e9,1e9,2.5e9]})}
    candles=pd.DataFrame({'time':pd.to_datetime(['2026-10-23T12:00Z','2026-10-23T12:05Z']),
                          'open':[6030.,6035.],'high':[6038.,6040.],'low':[6028.,6033.],'close':[6035.,6038.]})
    return result,{'candles':candles,'price':6042.,'timestamp':'2026-10-23T12:06:00+00:00'}


def test_candles_left_gex_right_share_vertical_prices_and_initial_range():
    result,market=inputs();figure=candles_gex_figure(result,40,market)
    candle=figure.data[0]
    assert candle.type=='candlestick' and candle.xaxis=='x' and candle.yaxis=='y'
    call=next(trace for trace in figure.data if trace.name=='Call GEX')
    put=next(trace for trace in figure.data if trace.name=='Put GEX')
    net=next(trace for trace in figure.data if trace.name=='NET GEX')
    assert call.orientation=='h' and call.xaxis=='x2' and call.yaxis=='y2'
    assert list(call.y)==[6020,6040,6060] and list(call.x)==[1,2,3]
    assert list(put.x)==[-2,-1,-.5] and list(net.x)==[-1,1,2.5]
    assert figure.layout.yaxis2.matches=='y'
    assert figure.layout.yaxis.range==figure.layout.yaxis2.range
    assert figure.layout.xaxis.domain[1]<figure.layout.xaxis2.domain[0]


def test_future_candles_are_not_shifted_again_and_spx_data_are_unchanged():
    result,market=inputs();source=copy.deepcopy(result);original=market['candles'].copy(deep=True)
    figure=candles_gex_figure(result,40,market)
    assert list(figure.data[0].open)==[6030,6035]
    pd.testing.assert_frame_equal(source['rows'],result['rows'])
    pd.testing.assert_frame_equal(original,market['candles'])
    assert result['spot']==6000 and result['call_wall']==6020
    for value in (6020,6045,6060,6040,6042):
        assert sum(shape.y0==value for shape in figure.layout.shapes)>=2


def test_call_green_put_red_and_zero_gex_axis_are_retained():
    result,market=inputs();figure=candles_gex_figure(result,40,market)
    call=next(t for t in figure.data if t.name=='Call GEX')
    put=next(t for t in figure.data if t.name=='Put GEX')
    assert call.marker.color=='#22b573' and put.marker.color=='#e64b4b'
    assert any(shape.x0==0 and shape.x1==0 and shape.xref=='x2' for shape in figure.layout.shapes)


def test_full_view_contains_all_strikes_and_candle_extremes_on_both_panels():
    result,market=inputs();market['candles'].loc[0,'low']=5000
    figure=candles_gex_figure(result,40,market,full=True)
    low,high=figure.layout.yaxis.range
    assert low<5000 and high>6060
    assert figure.layout.yaxis2.range==(low,high)


def test_quiet_session_fills_price_window_without_showing_entire_strike_universe():
    result,market=inputs()
    result['rows']=pd.concat([result['rows'],pd.DataFrame({
        'strike':[5400.,6600.],'call_gex':[100e9,100e9],
        'put_gex':[-90e9,-90e9],'net_gex':[10e9,10e9]})],ignore_index=True)
    zoom=candles_gex_figure(result,40,market)
    low,high=zoom.layout.yaxis.range
    assert 5980<low<6020 and 6060<high<6100
    assert high-low<150
    assert zoom.layout.xaxis2.range==pytest.approx((-3.3,3.3))
    # Out-of-window bars are retained with their actual values for full view/pan.
    call=next(trace for trace in zoom.data if trace.name=='Call GEX')
    assert list(call.x)[-2:]==[100,100]
    full=candles_gex_figure(result,40,market,full=True)
    assert full.layout.yaxis.range[0]<5440 and full.layout.yaxis.range[1]>6640
    assert full.layout.xaxis2.range==pytest.approx((-110,110))


def test_far_wall_does_not_compress_candles_but_remains_identified():
    result,market=inputs();result['call_wall']=6600
    figure=candles_gex_figure(result,40,market)
    low,high=figure.layout.yaxis.range
    assert high-low<150 and low<6028 and high>6042
    assert any(a.text=='Call Wall: 6,640.00' for a in figure.layout.annotations)
    assert any(s.y0==6640 for s in figure.layout.shapes)
    assert candles_gex_figure(result,40,market,full=True).layout.yaxis.range[1]>6640


def test_candle_extremes_stay_visible_even_when_quote_has_moved_far_from_photo():
    result,market=inputs()
    market['candles'][['open','high','low','close']]+=500
    market['price']+=500
    figure=candles_gex_figure(result,40,market)
    low,high=figure.layout.yaxis.range
    assert low<6528<6542<high and high-low<=100
    assert figure.layout.yaxis2.range==(low,high)
    assert all(np.isfinite(figure.layout.xaxis2.range))


def test_missing_candles_are_explicit_and_no_fake_time_series_is_added():
    result,_=inputs();figure=candles_gex_figure(result,40,None,empty_message='Candele non disponibili')
    assert all(trace.type!='candlestick' for trace in figure.data)
    assert len(figure.data)==3 and any(a.text=='Candele non disponibili' for a in figure.layout.annotations)
    assert figure.layout.yaxis.range==figure.layout.yaxis2.range
    assert figure.layout.xaxis.showticklabels is False and figure.layout.xaxis.title.text is None


def test_italian_axis_distinguishes_summer_and_winter_repeated_hour():
    result,market=inputs()
    market['candles']['time']=pd.to_datetime(['2026-10-25T00:30Z','2026-10-25T01:30Z'])
    figure=candles_gex_figure(result,40,market)
    assert list(figure.layout.xaxis.ticktext)==['02:30 CEST','02:30 CET']
