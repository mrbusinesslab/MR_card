"""Local clipboard actions for engineering addresses; no geocoding requests."""

def address_component(address):
    address=address.strip()
    if not address:
        return {'type':'text','text':'尚未填寫地址','size':'xs','color':'#64748B','wrap':True}
    return {'type':'button','style':'link','height':'sm','action':{'type':'clipboard','label':'複製地址','clipboardText':address}}
