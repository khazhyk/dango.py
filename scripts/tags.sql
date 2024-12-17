CREATE TABLE dango_tags (
    guild_id BIGINT NOT NULL,
    owner_id BIGINT NOT NULL,
    tag_name character varying NOT NULL,
    tag_content character varying NOT NULL,
    PRIMARY KEY (guild_id, tag_name)
);
