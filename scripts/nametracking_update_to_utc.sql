alter table namechanges alter column date set default (now() at time zone 'utc');
update namechanges SET date = date + 'X hours';
alter table nickchanges alter column date set default (now() at time zone 'utc');
update nickchanges SET date = date + 'X hours';
