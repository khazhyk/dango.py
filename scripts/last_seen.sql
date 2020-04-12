CREATE TABLE last_seen (
    id bigint,
    date timestamp with time zone DEFAULT (now() at time zone 'utc') NOT NULL,
    PRIMARY KEY (id)
);


CREATE TABLE last_spoke (
    id bigint,
    server_id bigint,
    date timestamp with time zone DEFAULT (now() at time zone 'utc') NOT NULL,
    PRIMARY KEY (id, server_id)
);
