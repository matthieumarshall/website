-- Seed initial placeholders for administration guides in static_pages table
INSERT INTO static_pages (slug, content)
VALUES
    ('athlete-registration-guide', '<h2>Athlete Registration Guide</h2><p>Guidance and instructions for registering athletes will be published here.</p>'),
    ('race-directors-guide', '<h2>Race Directors Guide</h2><p>Guidance and instructions for race directors will be published here.</p>'),
    ('suppliers-list', '<h2>Suppliers List</h2><p>Recommended league suppliers and service providers will be listed here.</p>'),
    ('team-managers-guide', '<h2>Team Managers Guide</h2><p>Guidance and instructions for team managers will be published here.</p>')
ON CONFLICT (slug) DO NOTHING;
