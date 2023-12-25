CREATE TABLE namechanges (
    id character varying NOT NULL,
    name bytea,
    date timestamp with time zone DEFAULT (now() at time zone 'utc') NOT NULL,
    idx integer DEFAULT 0 NOT NULL,
    PRIMARY KEY (id, idx)
);


CREATE TABLE nickchanges (
    id character varying NOT NULL,
    server_id character varying NOT NULL,
    name bytea,
    date timestamp with time zone DEFAULT (now() at time zone 'utc') NOT NULL,
    idx integer DEFAULT 0 NOT NULL,
    PRIMARY KEY (id, server_id, idx)
);
