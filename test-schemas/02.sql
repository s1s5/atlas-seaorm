CREATE TABLE "test_manager" ( "id" bigserial NOT NULL PRIMARY KEY, "name" varchar NOT NULL );
CREATE TABLE "test_user" ( "id" bigserial NOT NULL PRIMARY KEY, "name" varchar NOT NULL, "manager_id" bigint, CONSTRAINT "fk-user-to-manager"  FOREIGN KEY ("manager_id") REFERENCES "test_manager" ("id") ON DELETE CASCADE ON UPDATE CASCADE );
