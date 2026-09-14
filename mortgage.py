from datetime import date
def month_start(v):
    if isinstance(v,str): v=date.fromisoformat(v)
    return v.replace(day=1)
def add_month(v): return date(v.year+(v.month==12),1 if v.month==12 else v.month+1,1)
def payment(p,rate,n):
    r=rate/1200
    return p/n if not r else p*r*(1+r)**n/((1+r)**n-1)
def amortize(prop,db):
    principal=float(prop['original_loan']); rate=float(prop['interest_rate']); extra=float(prop['extra_payment']); regular=payment(principal,rate,int(prop['term_years'])*12); when=month_start(prop['loan_start_date']); changes=db.execute('select * from mortgage_change order by effective_date,id').fetchall(); ci=0; out=[]
    for num in range(1,1201):
        while ci<len(changes) and month_start(changes[ci]['effective_date'])<=when:
            c=changes[ci]; rate=float(c['interest_rate']) if c['interest_rate'] is not None else rate; extra=float(c['extra_payment']) if c['extra_payment'] is not None else extra; ci+=1
        interest=principal*rate/1200; paid=min(principal+interest,regular+extra); pp=paid-interest
        if pp<=0: break
        principal=max(0,principal-pp); out.append(dict(number=num,date=when,rate=rate,payment=paid,extra=min(extra,max(0,paid-regular)),principal=pp,interest=interest,balance=principal))
        if principal<.005: break
        when=add_month(when)
    return out
