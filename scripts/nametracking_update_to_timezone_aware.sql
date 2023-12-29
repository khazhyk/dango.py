start transaction;
ALTER TABLE namechanges RENAME COLUMN date TO old_date;
alter table namechanges add column date timestamp with time zone DEFAULT (now()) NOT NULL;
update namechanges set date = old_date at time zone 'utc';

ALTER TABLE nickchanges RENAME COLUMN date TO old_date;
alter table nickchanges add column date timestamp with time zone DEFAULT (now()) NOT NULL;
update nickchanges set date = old_date at time zone 'utc';
commit transaction;