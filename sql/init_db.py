"""Create the user_data table, seed rows for other users, and grant the Agent 2 database user.

Usage: python sql/init_db.py   (reads config from the environment; root password from Secret Manager)
"""
import os

from google.cloud import secretmanager
from google.cloud.sql.connector import Connector

P, L = os.environ["PROJECT_ID"], os.environ["REGION"]
INSTANCE, DB, USER = os.environ["SQL_INSTANCE"], os.environ["DB_NAME"], os.environ["DB_USER"]
ME = os.environ["DEMO_USER_EMAIL"]  # the user you will sign in with through IAP

sm = secretmanager.SecretManagerServiceClient()
root_pw = sm.access_secret_version(
    name=f"projects/{P}/secrets/{INSTANCE}-root-password/versions/latest").payload.data.decode()
connector = Connector()
conn = connector.connect(f"{P}:{L}:{INSTANCE}", "pymysql", user="root", password=root_pw, db=DB)
cur = conn.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS user_data (
  id INT AUTO_INCREMENT PRIMARY KEY,
  cookie VARCHAR(2048) NOT NULL,
  user VARCHAR(255) NOT NULL,
  note VARCHAR(255) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_cookie (cookie(255))
)""")
cur.execute("INSERT IGNORE INTO user_data (cookie, user, note) VALUES "
            "('seed-cookie-alice', 'alice@example.com', 'alice private note'), "
            "('seed-cookie-bob', 'bob@example.com', 'bob private note'), "
            "(%s, %s, %s)", (f"seed-cookie-{ME}", ME, f"profile note for {ME}"))
cur.execute(f"GRANT SELECT, INSERT, UPDATE ON {DB}.user_data TO '{USER}'@'%'")
conn.commit()
cur.execute("SELECT COUNT(*) FROM user_data")
print("rows", cur.fetchone()[0])
conn.close()
connector.close()
