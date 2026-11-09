-- Gastos por organización (ADR-0013). Ver postgresql/0005_expenses.sql: mismas tablas y columnas.
-- Importes en céntimos (enteros) para no arrastrar errores de coma flotante.

CREATE TABLE expenses (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    spent_on TEXT NOT NULL CHECK (spent_on GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    description TEXT NOT NULL CHECK (length(description) BETWEEN 1 AND 200),
    vendor TEXT CHECK (vendor IS NULL OR length(vendor) <= 120),
    category TEXT NOT NULL CHECK (length(category) BETWEEN 1 AND 40),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    vat_cents INTEGER NOT NULL DEFAULT 0 CHECK (vat_cents >= 0 AND vat_cents <= amount_cents),
    currency TEXT NOT NULL DEFAULT 'EUR' CHECK (length(currency) = 3),
    created_by TEXT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    deleted_at TIMESTAMP
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
