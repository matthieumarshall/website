-- The administration_sections/administration_documents sequences were never
-- advanced when the original rows were seeded (they were inserted with
-- explicit ids), so nextval() started returning ids that already exist,
-- causing "Duplicate key" constraint errors on new inserts. Burn through the
-- sequence values up to the current max id so future nextval() calls are safe.
SELECT nextval('administration_section_id_seq') FROM range((SELECT COALESCE(MAX(id), 0) FROM administration_sections));
SELECT nextval('administration_document_id_seq') FROM range((SELECT COALESCE(MAX(id), 0) FROM administration_documents));
