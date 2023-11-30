CREATE TABLE
    "test_manager" ("id" bigserial NOT NULL PRIMARY KEY, "name" VARCHAR NOT NULL);

CREATE TABLE
    "test_user" (
        "id" bigserial NOT NULL PRIMARY KEY,
        "name" VARCHAR NOT NULL,
        "manager_id" BIGINT NOT NULL,
        CONSTRAINT "fk-user-to-manager" FOREIGN KEY ("manager_id") REFERENCES "test_manager" ("id") ON DELETE CASCADE ON UPDATE CASCADE
    );