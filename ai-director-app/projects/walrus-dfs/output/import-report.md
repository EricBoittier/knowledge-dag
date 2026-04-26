# DaVinci Import Report

## Variant
- **default** (outputs under this variant's `output/` folder)

## Timeline index (ordered table)
- JSON: `/home/ericb/Documents/knowledge-dag/ai-director-app/projects/walrus-dfs/variants/default/output/timeline-index.json`
- Markdown table: `/home/ericb/Documents/knowledge-dag/ai-director-app/projects/walrus-dfs/variants/default/output/timeline-index.md`
- 32 row(s); spine length **59.544 s**

## Lane map
- Spine: main video clips
- Lane -1: narration
- Lane -2: dialogue captions (from script)
- Lane -3: studio text overlays (when enabled)
- Lane 1 / 2: studio media overlays (video/image / audio defaults)

## Checklist
- Import media first (source clip audio is muted in timeline)
- Import timeline_davinci_resolve.fcpxml
- Captions may be embedded in the FCPXML (`caption` elements); adjust in Inspector if needed
- Or import `subtitles.srt` as an additional subtitle track
- Narration.wav is the primary timeline audio track

## Validation
No missing media references detected.

## Video processing
Processed clips generated:
- seg_001: /home/ericb/Documents/knowledge-dag/ai-director-app/projects/walrus-dfs/variants/default/output/processed/seg_001_Emperor_Penguins_Nurture_a_Snowball_Dynasties_Preview_BBC_Earth_8d4015d9.normalized.styled.mov (crop=no, fx=3, lut=1)
- seg_002: /home/ericb/Documents/knowledge-dag/ai-director-app/projects/walrus-dfs/variants/default/output/processed/seg_002_Meet_the_Little_penguin_-_RAZOR_e120d9ae.normalized.styled.mov (crop=no, fx=3, lut=1)
- seg_003: /home/ericb/Documents/knowledge-dag/ai-director-app/projects/walrus-dfs/variants/default/output/processed/seg_003_The_Many_Different_Kinds_of_Penguins_Nat_Geo_Kids_Penguins_Playl_1a64a9c6.normalized.styled.mov (crop=no, fx=2, lut=0)
- seg_004: /home/ericb/Documents/knowledge-dag/ai-director-app/projects/walrus-dfs/variants/default/output/processed/seg_004_Atlantic_ice_Penguins_life._youtube_naturelovers_atlantic_pengui_8b9af885.normalized.styled.mov (crop=no, fx=3, lut=1)
- seg_005: /home/ericb/Documents/knowledge-dag/ai-director-app/projects/walrus-dfs/variants/default/output/processed/seg_005_Playful_baboon_performs_acrobatic_dive_into_the_water_9979d07b.normalized.styled.mov (crop=no, fx=3, lut=0)
- seg_007: /home/ericb/Documents/knowledge-dag/ai-director-app/projects/walrus-dfs/variants/default/output/processed/seg_007_penguin_adaptations_-_year_2_f81a39eb.normalized.styled.mov (crop=no, fx=3, lut=1)
- seg_008: /home/ericb/Documents/knowledge-dag/ai-director-app/projects/walrus-dfs/variants/default/output/processed/seg_008_Why_are_there_no_penguins_in_Iceland_b904e63a.normalized.styled.mov (crop=no, fx=3, lut=1)
- seg_009: /home/ericb/Documents/knowledge-dag/ai-director-app/projects/walrus-dfs/variants/default/output/processed/seg_009_Penguin_Threats_Predators_Pets_Animals_Facts_2109326f.normalized.styled.mov (crop=no, fx=3, lut=1)
- seg_010: /home/ericb/Documents/knowledge-dag/ai-director-app/projects/walrus-dfs/variants/default/output/processed/seg_010__A_Place_for_Penguins_-_Offical_2019_WCFF_Trailer_27485d0c.normalized.styled.mov (crop=no, fx=3, lut=1)
- seg_011: /home/ericb/Documents/knowledge-dag/ai-director-app/projects/walrus-dfs/variants/default/output/processed/seg_011_Arctic_Connected_Sea_ice_loss_and_climate_change_7af3bb05.normalized.styled.mov (crop=no, fx=2, lut=1)
- seg_012: /home/ericb/Documents/knowledge-dag/ai-director-app/projects/walrus-dfs/variants/default/output/processed/seg_012_Chinas_Overfishing_Crisis_How_One_Fleet_Is_Devastating_the_World_8df9e758.normalized.styled.mov (crop=no, fx=2, lut=0)
- seg_013: /home/ericb/Documents/knowledge-dag/ai-director-app/projects/walrus-dfs/variants/default/output/processed/seg_013_Penguin_Life_Cycle_for_Kids_Learn_About_a_Penguin_s_Life_Fun_Ani_b512f6da.normalized.styled.mov (crop=no, fx=3, lut=0)
- ml_1777195686414: /home/ericb/Documents/knowledge-dag/ai-director-app/projects/walrus-dfs/variants/default/output/processed/overlay_ml_1777195686414.still.mov (studio image → processed)
- ml_1777195689983: /home/ericb/Documents/knowledge-dag/ai-director-app/projects/walrus-dfs/variants/default/output/processed/overlay_ml_1777195689983.still.mov (studio image → processed)
- ml_1777196187546: /home/ericb/Documents/knowledge-dag/ai-director-app/projects/walrus-dfs/variants/default/output/processed/overlay_ml_1777196187546.still.mov (studio image → processed)

## Project root output (mirror)
The build CLI also copies this FCPXML, this report, `export-manifest.json`, `timeline-index.json`, `timeline-index.md`, and `crop-validation.json` to:
- `/home/ericb/Documents/knowledge-dag/ai-director-app/projects/walrus-dfs/output`
Narration (`narration.wav`) and `processed/` clips remain under the variant `output/` folder; FCPXML `file://` paths point to those absolute locations.

## Crop validation
- No segments required crop validation.
