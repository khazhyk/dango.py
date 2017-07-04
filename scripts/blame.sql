CREATE TABLE blame (
	id BIGINT PRIMARY KEY,
	message_id BIGINT NOT NULL,
	author_id BIGINT NOT NULL,
	channel_id BIGINT NOT NULL,
	server_id BIGINT
);
