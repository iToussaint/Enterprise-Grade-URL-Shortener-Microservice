"""seed default tags

Revision ID: 72e9c09102cd
Revises: 43ca2d65d774
Create Date: 2026-11-15 10:30:36.962555

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert

# revision identifiers, used by Alembic.
revision = "72e9c09102cd"
down_revision = "43ca2d65d774"
branch_labels = None
depends_on = None

DEFAULT_TAGS = ["Marketing", "Social", "Newsletter", "Product", "Event"]

# The table as it is at this revision. Data migrations never import the app's
# models: the models keep changing, and this migration must keep working.
tags = sa.table("tags", sa.column("id", sa.Integer), sa.column("name", sa.String))


def upgrade():
    # Tags that already exist (e.g. created by a user) are left as they are.
    op.execute(
        insert(tags)
        .values([{"name": name} for name in DEFAULT_TAGS])
        .on_conflict_do_nothing(index_elements=["name"])
    )


def downgrade():
    op.execute(tags.delete().where(tags.c.name.in_(DEFAULT_TAGS)))
