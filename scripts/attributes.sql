CREATE TABLE attributes (
    id character varying NOT NULL,
    type character varying NOT NULL,
    data jsonb,
    PRIMARY KEY (id, type)
);
