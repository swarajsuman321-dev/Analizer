"""Stable per-channel colors shared by interactive plots and report exports."""
import colorsys

PALETTE=['#58b6ff','#ffb454','#79dba8','#d4a1ff','#ff8096','#e5da69','#83e1e8']


def channel_colors(store):
    """Keep saved/user colors; allocate distinct colors to new channels.

    Automatic colors live in channel metadata, so hiding, closing another file,
    or restoring a workspace does not change the meaning of a legend color.
    """
    result={};used=set()
    for id,channel in store.channels.items():
        color=channel.attributes.get('plot_style',{}).get('color') or channel.attributes.get('trace_color')
        if color and (channel.attributes.get('plot_style',{}).get('color') or color.lower() not in used):result[id]=color;used.add(color.lower())
    index=0
    for id,channel in store.channels.items():
        if id in result:continue
        while True:
            if index<len(PALETTE):color=PALETTE[index]
            else:
                rgb=colorsys.hsv_to_rgb((index*.61803398875)%1,.57,.95)
                color='#'+''.join(f'{round(value*255):02x}' for value in rgb)
            index+=1
            if color.lower() not in used:break
        channel.attributes['trace_color']=color;result[id]=color;used.add(color.lower())
    return result
