db = db.getSiblingDB("analytics");

db.createCollection("csv_metadata");
db.createCollection("processing_results");
db.createCollection("users");

// Indexes
db.csv_metadata.createIndex({ upload_id: 1 }, { unique: true });
db.csv_metadata.createIndex({ user_id: 1 });
db.csv_metadata.createIndex({ created_at: -1 });

db.processing_results.createIndex({ upload_id: 1 }, { unique: true });
db.processing_results.createIndex({ status: 1 });

db.users.createIndex({ email: 1 }, { unique: true });

print("analytics DB initialized");