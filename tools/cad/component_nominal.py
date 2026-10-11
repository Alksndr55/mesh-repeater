"""Bare PCB nominal labels; electrical Value/MPN/package remain intact."""
def nominal(part):
    ref=part['ref'];value=part['value']
    if part['kind'] in ('TestPoint','MountingHole','NetTie'):return ''
    if ref in ('C53','C54','C55'):return ''
    variants={'R3':'Na:6.34k\nLTO:13k','R4':'Na:10k\nLTO:10.5k','C30':'Na:12pF\nLTO:6.8pF'}
    if ref in ('R3','R4') and part.get('value_lto2s'):
        variants[ref]='Na:'+value.split()[0]+'\nLTO:'+part['value_lto2s'].split()[0]
    if part.get('value_lto2s') and ref=='R15':variants[ref]='Na:40.2k\nLTO:130k'
    if part.get('value_lto2s') and ref=='R16':variants[ref]='Na:49.9k\nLTO:49.9k'
    if ref=='R56' and part.get('value_lto2s'):
        variants[ref]='Na:1.8R\nLTO:0R'
    if ref in variants:return variants[ref]
    names={'M1':'NiceNano','M2':'HT-RA62','SH1':'SHIELD','BT1':'CR2032',
           'J3':'I2C','J4':'GPS','J5':'UART','J7':'SOLAR','J8':'BAT',
           'J10':'ISP','J11':'LC/SYS','J12':'BAT/MID',
           'SW1':'USER','SW2':'RESET','FB1':'60R@100MHz',
           'U4':'DS3231M','U6':'ATtiny13A','TH1':'10k NTC'}
    if ref in names:return names[ref]
    return value.split()[0]
