create table if not exists property(id integer primary key check(id=1),name text,address text,purchase_price real,original_loan real,interest_rate real,term_years integer,loan_start_date text,extra_payment real default 0);
create table if not exists one_time_cost(id integer primary key autoincrement,category text,description text,amount real,cost_date text);
create table if not exists recurring_item(id integer primary key autoincrement,kind text check(kind in('income','expense')),category text,description text,monthly_amount real,effective_start text,effective_end text);
create table if not exists mortgage_change(id integer primary key autoincrement,effective_date text,interest_rate real,extra_payment real,note text);
