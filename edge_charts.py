"""Aligned price/GEX presentation. No calculations or source data are changed."""
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from zoneinfo import ZoneInfo

CALL = '#22b573'
PUT = '#e64b4b'
NET = '#f4a2b3'
FLIP = '#e7ae4e'


def _price_limits(result, shift, market, levels, full):
    """Frame candles and nearby references, not the entire strike universe."""
    photo = result['spot'] + shift
    candles = market['candles'] if market is not None else None
    anchor = market['price'] if market is not None else photo
    prices = [anchor]
    if candles is not None and not candles.empty:
        prices += [float(candles.low.min()), float(candles.high.max())]
    references = [photo] + [value for _, value, _ in levels]
    if full:
        prices += references + list(result['rows'].strike + shift)
    else:
        # Distant walls remain in the header and in Vista completa. They must
        # not compress a quiet price session into a few pixels.
        low, high = min(prices), max(prices)
        prices += [value for value in references if low - 100 <= value <= high + 100]
    center = (min(prices) + max(prices)) / 2
    height = max(prices) - min(prices)
    span = max(40., height / 2 + max(10., height * .08))
    return [center - span, center + span]


def candles_gex_figure(result, shift=0., market=None, *, full=False, empty_message=None):
    """Prices rise vertically on both panels; candles left, signed GEX right."""
    candles = market['candles'] if market is not None else None
    figure = make_subplots(rows=1,cols=2,shared_yaxes=True,horizontal_spacing=.04,
                           column_widths=[.65,.35],subplot_titles=('Prezzo · candele 5 minuti','Profilo GEX Edge'))
    if candles is not None and not candles.empty:
        figure.add_trace(go.Candlestick(
            x=candles.time,open=candles.open,high=candles.high,low=candles.low,close=candles.close,
            name='Candele 5m concluse',increasing_line_color=CALL,decreasing_line_color=PUT,
            hoverinfo='text',hovertext=[row.time.tz_convert('Europe/Rome').strftime('%d/%m/%Y %H:%M:%S %Z')+
                                       f'<br>O {row.open:.2f} · H {row.high:.2f} · L {row.low:.2f} · C {row.close:.2f}'
                                       for row in candles.itertuples()]),row=1,col=1)
        ticks = candles.time.iloc[::max(1,len(candles)//7)]
        figure.update_xaxes(tickmode='array',tickvals=list(ticks),
                            ticktext=[stamp.tz_convert('Europe/Rome').strftime('%H:%M %Z') for stamp in ticks],
                            row=1,col=1)
    else:
        figure.add_annotation(x=.5,y=.5,xref='x domain',yref='y domain',showarrow=False,
                              text=empty_message or 'Candele non disponibili',font=dict(size=14),
                              bgcolor='rgba(14,17,23,0.9)',borderpad=10)
        figure.update_xaxes(showticklabels=False,showgrid=False,zeroline=False,row=1,col=1)
    if market is not None:
        figure.add_scatter(x=[market['timestamp']],y=[market['price']],mode='markers',
                           marker=dict(color='#facc15',size=9),name='Ultimo prezzo disponibile',
                           text=[datetime.fromisoformat(market['timestamp']).astimezone(ZoneInfo('Europe/Rome')).strftime('%d/%m/%Y %H:%M:%S %Z')],
                           hovertemplate='%{text}<br>Prezzo %{y:.2f}<extra></extra>',row=1,col=1)
    frame = result['rows']
    figure.add_bar(x=frame.call_gex/1e9,y=frame.strike+shift,orientation='h',
                   name='Call GEX',marker_color=CALL,row=1,col=2)
    figure.add_bar(x=frame.put_gex/1e9,y=frame.strike+shift,orientation='h',
                   name='Put GEX',marker_color=PUT,row=1,col=2)
    figure.add_scatter(x=frame.net_gex/1e9,y=frame.strike+shift,mode='lines',
                       name='NET GEX',line=dict(color=NET,width=2),row=1,col=2)
    levels = [(label,result[key]+shift,color) for label,key,color in
              (('Put Wall','put_wall',PUT),('Gamma Flip','flip',FLIP),('Call Wall','call_wall',CALL))
              if result[key] is not None]
    for index,(label,value,color) in enumerate(levels):
        for column in (1,2):
            figure.add_hline(y=value,line_color=color,line_dash='dash',line_width=1.3,
                             row=1,col=column,exclude_empty_subplots=False)
        figure.add_annotation(x=(index+.5)/max(1,len(levels)),y=1.12,xref='paper',yref='paper',
                              text=f'{label}: {value:,.2f}',showarrow=False,
                              font=dict(color=color,size=12),bgcolor='rgba(15,22,33,0.9)',borderpad=4)
    photo = result['spot']+shift
    for column in (1,2):
        figure.add_hline(y=photo,line_color='#b5c6de',line_dash='dot',row=1,col=column,
                         exclude_empty_subplots=False)
        if market is not None:
            figure.add_hline(y=market['price'],line_color='#facc15',line_width=1,row=1,col=column,
                             exclude_empty_subplots=False)
    figure.add_vline(x=0,line_color='#738198',line_width=1,row=1,col=2)
    limits = _price_limits(result, shift, market, levels, full)
    # Plotly's autorange includes off-screen strike bars. Scale GEX to the
    # initial visible prices while retaining every original trace value.
    visible = frame if full else frame.loc[(frame.strike+shift).between(*limits)]
    exposures = [0.] + [float(value)/1e9 for key in ('call_gex','put_gex','net_gex') for value in visible[key]]
    extent = max(abs(min(exposures)), abs(max(exposures)), .01) * 1.1
    figure.update_xaxes(range=[-extent,extent],row=1,col=2)
    # Explicit equal ranges plus matches keep zoom/pan and initial view aligned.
    figure.update_yaxes(range=limits,nticks=12,row=1,col=1)
    figure.update_yaxes(range=limits,matches='y',showticklabels=True,nticks=12,row=1,col=2)
    figure.update_xaxes(title='Ora italiana · chiusura candela' if candles is not None and not candles.empty else None,
                        rangeslider_visible=False,row=1,col=1)
    figure.update_xaxes(title=f"GEX {result['symbol']} · miliardi USD/1%",zeroline=True,row=1,col=2)
    figure.update_layout(height=620,barmode='relative',margin=dict(t=105,b=85,l=35,r=35),
                         legend=dict(orientation='h',y=-.16,x=.5,xanchor='center'),hovermode='closest',
                         uirevision=f"price-focus-v2/{result.get('sha256','')}/{shift}/{full}")
    return figure
