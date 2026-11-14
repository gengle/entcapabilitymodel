-- generated; SQLite
PRAGMA foreign_keys=ON;
CREATE TABLE capability(id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, name TEXT NOT NULL, parent_id INTEGER REFERENCES capability(id), level INTEGER NOT NULL, owner TEXT, criticality TEXT, review_cycle_days INTEGER, maturity TEXT, lifecycle TEXT);
CREATE TABLE entity_type(name TEXT PRIMARY KEY, parent TEXT REFERENCES entity_type(name));
CREATE TABLE entity(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, type TEXT NOT NULL REFERENCES entity_type(name), props TEXT NOT NULL DEFAULT '{}');
CREATE TABLE relation_type(name TEXT PRIMARY KEY, inverse TEXT, from_types TEXT, to_types TEXT, transitive INTEGER, min_level INTEGER);
CREATE TABLE link(id INTEGER PRIMARY KEY, src INTEGER NOT NULL REFERENCES entity(id), relation TEXT NOT NULL REFERENCES relation_type(name), cap_id INTEGER REFERENCES capability(id), ent_id INTEGER REFERENCES entity(id), attrs TEXT NOT NULL DEFAULT '{}', CHECK((cap_id IS NULL) <> (ent_id IS NULL)));
CREATE INDEX link_rel ON link(relation, cap_id);
INSERT INTO capability VALUES(1,'Finance','Finance',NULL,1,'CFO Office','high','90','initial','active');
INSERT INTO capability VALUES(2,'Finance/Accounts Payable','Accounts Payable',1,2,'Dana Reyes','high','90','initial','active');
INSERT INTO capability VALUES(3,'Finance/Accounts Payable/Invoice Management','Invoice Management',2,3,'Dana Reyes','high','90','initial','active');
INSERT INTO capability VALUES(4,'Finance/Accounts Payable/Invoice Management/Invoice Capture','Invoice Capture',3,4,'Dana Reyes','high','90','defined','active');
INSERT INTO capability VALUES(5,'Finance/Accounts Payable/Invoice Management/Three-Way Matching','Three-Way Matching',3,4,'Dana Reyes','high','90','pilot','active');
INSERT INTO capability VALUES(6,'Finance/Accounts Payable/Invoice Management/Invoice Approval','Invoice Approval',3,4,'Dana Reyes','high','90','defined','active');
INSERT INTO capability VALUES(7,'Finance/Accounts Payable/Supplier Payments','Supplier Payments',2,3,'Dana Reyes','high','90','optimized','active');
INSERT INTO capability VALUES(8,'Finance/Accounts Payable/Supplier Payments/Payment Run','Payment Run',7,4,'Dana Reyes','high','90','optimized','active');
INSERT INTO capability VALUES(9,'Finance/Accounts Payable/Supplier Payments/Payment Reconciliation','Payment Reconciliation',7,4,'Dana Reyes','high','90','defined','active');
INSERT INTO capability VALUES(10,'Finance/Financial Planning','Financial Planning',1,2,'CFO Office','medium','90','initial','active');
INSERT INTO capability VALUES(11,'Finance/Financial Planning/Budgeting','Budgeting',10,3,'CFO Office','medium','90','defined','active');
INSERT INTO capability VALUES(12,'Finance/Financial Planning/Forecasting','Forecasting',10,3,'CFO Office','medium','90','initial','active');
INSERT INTO capability VALUES(13,'Human Resources','Human Resources',NULL,1,'CHRO Office','medium','180','initial','active');
INSERT INTO capability VALUES(14,'Human Resources/Talent Acquisition','Talent Acquisition',13,2,'CHRO Office','medium','180','initial','active');
INSERT INTO capability VALUES(15,'Human Resources/Talent Acquisition/Recruiting','Recruiting',14,3,'CHRO Office','medium','180','initial','active');
INSERT INTO capability VALUES(16,'Human Resources/Talent Acquisition/Recruiting/Candidate Sourcing','Candidate Sourcing',15,4,'CHRO Office','medium','180','defined','active');
INSERT INTO capability VALUES(17,'Human Resources/Talent Acquisition/Recruiting/Interview Scheduling','Interview Scheduling',15,4,'CHRO Office','medium','180','initial','active');
INSERT INTO capability VALUES(18,'Human Resources/Talent Acquisition/Onboarding','Onboarding',14,3,'CHRO Office','medium','180','initial','active');
INSERT INTO capability VALUES(19,'Technology','Technology',NULL,1,'CIO Office','high','180','initial','active');
INSERT INTO capability VALUES(20,'Technology/Security','Security',19,2,'CIO Office','high','180','initial','active');
INSERT INTO capability VALUES(21,'Technology/Security/Access Management','Access Management',20,3,'CIO Office','high','180','initial','active');
INSERT INTO capability VALUES(22,'Technology/Security/Access Management/Single Sign-On','Single Sign-On',21,4,'CIO Office','high','180','optimized','active');
INSERT INTO capability VALUES(23,'Technology/Security/Access Management/Privileged Access','Privileged Access',21,4,'CIO Office','high','180','initial','active');
INSERT INTO entity_type VALUES('Asset',NULL);
INSERT INTO entity_type VALUES('Application','Asset');
INSERT INTO entity_type VALUES('Service','Asset');
INSERT INTO entity_type VALUES('Team',NULL);
INSERT INTO entity VALUES(1,'SAP S/4','Application','{"owner": "Finance IT", "lifecycle": "active", "vendor": "SAP"}');
INSERT INTO entity VALUES(2,'ApproveIt','Application','{"owner": "Finance IT", "lifecycle": "active", "vendor": null}');
INSERT INTO entity VALUES(3,'OCR Capture','Application','{"owner": null, "lifecycle": "active", "vendor": "ScanCo"}');
INSERT INTO entity VALUES(4,'Match Engine','Application','{"owner": "Finance IT", "lifecycle": "active", "vendor": null}');
INSERT INTO entity VALUES(5,'Talent Platform','Application','{"owner": null, "lifecycle": "active", "vendor": "Acme HR Cloud"}');
INSERT INTO entity VALUES(6,'Corporate SSO','Service','{"owner": "Identity Team", "lifecycle": "active"}');
INSERT INTO entity VALUES(7,'AP Operations','Team','{"head": "Dana Reyes", "lifecycle": "active"}');
INSERT INTO relation_type VALUES('exposes','exposed_by','Asset|Team','Capability',0,3);
INSERT INTO relation_type VALUES('requires','required_by','Asset|Team','Capability',0,3);
INSERT INTO relation_type VALUES('depends_on','dependents','Application','Application|Service',1,NULL);
INSERT INTO link(src,relation,cap_id,ent_id,attrs) VALUES(1,'exposes',6,NULL,'{}');
INSERT INTO link(src,relation,cap_id,ent_id,attrs) VALUES(1,'exposes',8,NULL,'{}');
INSERT INTO link(src,relation,cap_id,ent_id,attrs) VALUES(1,'exposes',11,NULL,'{"coverage": "partial"}');
INSERT INTO link(src,relation,cap_id,ent_id,attrs) VALUES(2,'exposes',6,NULL,'{"coverage": "partial"}');
INSERT INTO link(src,relation,cap_id,ent_id,attrs) VALUES(2,'requires',22,NULL,'{}');
INSERT INTO link(src,relation,cap_id,ent_id,attrs) VALUES(2,'requires',23,NULL,'{}');
INSERT INTO link(src,relation,cap_id,ent_id,attrs) VALUES(2,'depends_on',NULL,1,'{"criticality": "high"}');
INSERT INTO link(src,relation,cap_id,ent_id,attrs) VALUES(3,'exposes',4,NULL,'{}');
INSERT INTO link(src,relation,cap_id,ent_id,attrs) VALUES(3,'requires',22,NULL,'{}');
INSERT INTO link(src,relation,cap_id,ent_id,attrs) VALUES(3,'depends_on',NULL,6,'{}');
INSERT INTO link(src,relation,cap_id,ent_id,attrs) VALUES(4,'exposes',5,NULL,'{"coverage": "partial"}');
INSERT INTO link(src,relation,cap_id,ent_id,attrs) VALUES(4,'requires',4,NULL,'{}');
INSERT INTO link(src,relation,cap_id,ent_id,attrs) VALUES(4,'depends_on',NULL,3,'{"criticality": "high"}');
INSERT INTO link(src,relation,cap_id,ent_id,attrs) VALUES(5,'exposes',15,NULL,'{}');
INSERT INTO link(src,relation,cap_id,ent_id,attrs) VALUES(5,'requires',22,NULL,'{}');
INSERT INTO link(src,relation,cap_id,ent_id,attrs) VALUES(6,'exposes',22,NULL,'{}');
INSERT INTO link(src,relation,cap_id,ent_id,attrs) VALUES(7,'exposes',9,NULL,'{}');
INSERT INTO link(src,relation,cap_id,ent_id,attrs) VALUES(7,'exposes',6,NULL,'{"coverage": "partial"}');
CREATE VIEW entity_active AS SELECT * FROM entity WHERE COALESCE(json_extract(props,'$.lifecycle'),'active')<>'retire';
CREATE VIEW unmet_requires AS SELECT e.name AS entity, c.path AS capability, json_extract(l.attrs,'$.dependency') AS severity
  FROM link l JOIN entity_active e ON e.id=l.src JOIN capability c ON c.id=l.cap_id WHERE l.relation='requires' AND NOT EXISTS (
    SELECT 1 FROM link p JOIN entity_active pe ON pe.id=p.src JOIN capability pc ON pc.id=p.cap_id
    WHERE p.relation IN ('exposes') AND pe.id<>l.src AND (pc.path=c.path OR pc.path LIKE c.path||'/%'));
CREATE VIEW coverage AS SELECT c.path, c.level, (SELECT COUNT(DISTINCT p.src) FROM link p JOIN entity_active pe ON pe.id=p.src JOIN capability pc ON pc.id=p.cap_id
  WHERE p.relation IN ('exposes') AND (pc.path=c.path OR pc.path LIKE c.path||'/%')) AS providers FROM capability c WHERE c.level>=3;
CREATE VIEW depends_on_closure AS WITH RECURSIVE r(src,dst) AS (SELECT src,ent_id FROM link WHERE relation='depends_on' AND ent_id IS NOT NULL
  UNION SELECT r.src,l.ent_id FROM r JOIN link l ON l.src=r.dst WHERE l.relation='depends_on' AND l.ent_id IS NOT NULL)
  SELECT a.name AS src, b.name AS dst FROM r JOIN entity a ON a.id=r.src JOIN entity b ON b.id=r.dst;
