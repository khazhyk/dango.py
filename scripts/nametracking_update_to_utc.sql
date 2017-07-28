start transaction;
alter table namechanges alter column date set default (now() at time zone 'utc');
update namechanges SET date = date + '5 hours';
alter table nickchanges alter column date set default (now() at time zone 'utc');
update nickchanges SET date = date + '5 hours';
commit transaction;





# Try two

create temp table temp_namechanges as select * from namechanges;
copy namechanges to '/tmp/namechanges_bak';
update temp_namechanges set date = date + '5 hours';
drop table namechanges;
create table namechanges as select * from temp_namechanges;
alter table namechanges alter column id set not null;
alter table namechanges alter column idx set not null;
alter table namechanges alter column idx set default 0;
alter table namechanges alter column date set not null;
alter table namechanges alter column date set default (now() at time zone 'utc');
alter table namechanges add primary key (id, idx);


create temp table temp_nickchanges as select * from nickchanges;
copy nickchanges to '/tmp/nickchanges_bak';
update temp_nickchanges set date = date + '5 hours';
drop table nickchanges;
create table nickchanges as select * from temp_nickchanges;
alter table nickchanges alter column id set not null;
alter table nickchanges alter column server_id set not null;
alter table nickchanges alter column idx set not null;
alter table nickchanges alter column idx set default 0;
alter table nickchanges alter column date set not null;
alter table nickchanges alter column date set default (now() at time zone 'utc');
alter table nickchanges add primary key (id, server_id, idx);
