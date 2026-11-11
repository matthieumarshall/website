-- Correct a known transcription error in results and stored standings.
UPDATE results SET athlete_name = 'Victoria Bödeker'
WHERE athlete_name = 'Victoria B÷deker';

UPDATE individual_standings SET athlete_name = 'Victoria Bödeker'
WHERE athlete_name = 'Victoria B÷deker';

-- Scoring members are JSON and may contain either literal or escaped Unicode.
UPDATE team_round_results
SET scoring_members = replace(
    replace(scoring_members, 'Victoria B÷deker (', 'Victoria Bödeker ('),
    'Victoria B' || chr(92) || 'u00f7deker (',
    'Victoria B' || chr(92) || 'u00f6deker ('
)
WHERE contains(scoring_members, 'Victoria B÷deker (')
   OR contains(scoring_members, 'Victoria B' || chr(92) || 'u00f7deker (');
