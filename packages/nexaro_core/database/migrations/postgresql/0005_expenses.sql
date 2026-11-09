-- Gastos por organización (ADR-0013). Mismas tablas y columnas que sqlite/0005_expenses.sql.

CREATE TABLE expenses (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    spent_on date NOT NULL,
    description text NOT NULL CHECK (length(description) BETWEEN 1 AND 200),
    vendor text CHECK (vendor IS NULL OR length(vendor) <= 120),
    category text NOT NULL CHECK (length(category) BETWEEN 1 AND 40),
    amount_cents bigint NOT NULL CHECK (amount_cents > 0),
    vat_cents bigint NOT NULL DEFAULT 0 CHECK (vat_cents >= 0 AND vat_cents <= amount_cents),
    currency text NOT NULL DEFAULT 'EUR' CHECK (length(currency) = 3),
    created_by uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz,
    deleted_at timestamptz
);
CREATE INDEX idx_expenses_org_date ON expenses(organization_id, spent_on);

INSERT INTO permissions (id, description) VALUES
    ('expenses:read', 'Ver gastos y su resumen'),
    ('expenses:write', 'Registrar, editar y borrar gastos');
INSERT INTO role_permissions (role_id, permission_id) VALUES
    ('owner', 'expenses:read'),
    ('owner', 'expenses:write'),
    ('admin', 'expenses:read'),
    ('admin', 'expenses:write');

ALTER TABLE expenses ENABLE ROW LEVEL SECURITY;
ALTER TABLE expenses FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON expenses
    USING (organization_id = nullif(current_setting('nexaro.organization_id', true), '')::uuid)
    WITH CHECK (organization_id = nullif(current_setting('nexaro.organization_id', true), '')::uuid);
