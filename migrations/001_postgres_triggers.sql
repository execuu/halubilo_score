-- Tables live in halubilo, outside Supabase's exposed public schema.
CREATE FUNCTION enforce_score_max() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.score > (SELECT max_score FROM activity WHERE id = NEW.activity_id) THEN
        RAISE EXCEPTION 'score exceeds activity maximum' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER score_max_insert BEFORE INSERT OR UPDATE ON score
FOR EACH ROW EXECUTE FUNCTION enforce_score_max();

CREATE FUNCTION enforce_activity_max() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.max_score < (SELECT MAX(score) FROM score WHERE activity_id = NEW.id) THEN
        RAISE EXCEPTION 'maximum below recorded score' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER activity_max_update BEFORE UPDATE OF max_score ON activity
FOR EACH ROW EXECUTE FUNCTION enforce_activity_max();

CREATE FUNCTION preserve_audit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit history is append-only' USING ERRCODE = '23514';
END $$;
CREATE TRIGGER audit_no_change BEFORE UPDATE OR DELETE OR TRUNCATE ON audit
FOR EACH STATEMENT EXECUTE FUNCTION preserve_audit();
