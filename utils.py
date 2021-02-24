import datetime


def datestr_to_date(datestr):
    """
    Parse year/month/day string to datetime.date
    """
    datestr = datestr.replace('-', '/')
    yr, mo, dy = datestr.split('/')
    date = datetime.date(int(yr), int(mo), int(dy))
    return date