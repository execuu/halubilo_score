-- Initial fresh-event schema. Never apply to an inherited unversioned database.

BEGIN IMMEDIATE;


CREATE TABLE activity (
	id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description TEXT NOT NULL, 
	max_score INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (max_score BETWEEN 1 AND 1000), 
	UNIQUE (name)
)

;


CREATE TABLE audit (
	id INTEGER NOT NULL, 
	actor VARCHAR(100) NOT NULL, 
	action VARCHAR(80) NOT NULL, 
	entity VARCHAR(100) NOT NULL, 
	reason TEXT NOT NULL, 
	"before" JSON, 
	"after" JSON, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE INDEX ix_audit_created_at ON audit (created_at);


CREATE TABLE event_state (
	id INTEGER NOT NULL, 
	scoring_open BOOLEAN NOT NULL, 
	revision INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (id = 1)
)

;


CREATE TABLE login_attempt (
	"key" VARCHAR(64) NOT NULL, 
	count INTEGER NOT NULL, 
	expires INTEGER NOT NULL, 
	PRIMARY KEY ("key")
)

;

CREATE INDEX ix_login_attempt_expires ON login_attempt (expires);


CREATE TABLE schema_version (
	version INTEGER NOT NULL, 
	PRIMARY KEY (version)
)

;


CREATE TABLE team (
	id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	image_filename VARCHAR(255), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
)

;


CREATE TABLE user (
	id INTEGER NOT NULL, 
	username VARCHAR(80) NOT NULL, 
	email VARCHAR(120) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	activity_id INTEGER, 
	enabled BOOLEAN NOT NULL, 
	auth_version INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (role IN ('admin', 'user')), 
	UNIQUE (username), 
	UNIQUE (email), 
	FOREIGN KEY(activity_id) REFERENCES activity (id) ON DELETE RESTRICT
)

;

CREATE INDEX ix_user_activity_id ON user (activity_id);


CREATE TABLE score (
	id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, 
	team_id INTEGER NOT NULL, 
	activity_id INTEGER NOT NULL, 
	score INTEGER NOT NULL, 
	notes TEXT NOT NULL, 
	created_by INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	version INTEGER NOT NULL, 
	CONSTRAINT one_score_per_activity UNIQUE (team_id, activity_id), 
	CHECK (score >= 0), 
	FOREIGN KEY(team_id) REFERENCES team (id) ON DELETE RESTRICT, 
	FOREIGN KEY(activity_id) REFERENCES activity (id) ON DELETE RESTRICT, 
	FOREIGN KEY(created_by) REFERENCES user (id) ON DELETE RESTRICT
)

;

CREATE INDEX ix_score_created_by ON score (created_by);

CREATE INDEX ix_score_created_at ON score (created_at);

CREATE INDEX ix_score_activity_id ON score (activity_id);

INSERT INTO schema_version (version) VALUES (1);

INSERT INTO event_state (id, scoring_open, revision) VALUES (1, 1, 1);

CREATE TRIGGER score_max_insert BEFORE INSERT ON score WHEN NEW.score > (SELECT max_score FROM activity WHERE id = NEW.activity_id) BEGIN SELECT RAISE(ABORT, 'score exceeds activity maximum'); END;

CREATE TRIGGER score_max_update BEFORE UPDATE ON score WHEN NEW.score > (SELECT max_score FROM activity WHERE id = NEW.activity_id) BEGIN SELECT RAISE(ABORT, 'score exceeds activity maximum'); END;

CREATE TRIGGER activity_max_update BEFORE UPDATE OF max_score ON activity WHEN NEW.max_score < (SELECT MAX(score) FROM score WHERE activity_id = NEW.id) BEGIN SELECT RAISE(ABORT, 'maximum below recorded score'); END;

CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT, 'audit history is append-only'); END;

CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT, 'audit history is append-only'); END;

COMMIT;
