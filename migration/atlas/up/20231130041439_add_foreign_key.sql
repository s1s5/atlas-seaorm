-- Modify "test_user" table
ALTER TABLE "test_user" ADD COLUMN "manager_id" bigint NULL, ADD
 CONSTRAINT "fk-user-to-manager" FOREIGN KEY ("manager_id") REFERENCES "test_manager" ("id") ON UPDATE CASCADE ON DELETE CASCADE;
