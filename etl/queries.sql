-- V1 Typed view over the raw landing table (schema applied on read)
DROP VIEW IF EXISTS v_requests;
CREATE VIEW v_requests AS
SELECT
    rowid AS landing_row,
    CASE
        WHEN received GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*' THEN substr(received, 1, 7)
        WHEN received GLOB '[0-9][0-9]/[0-9][0-9]/[0-9][0-9][0-9][0-9]*' AND substr(received, 1, 2) != '00'
            THEN substr(received, 7, 4) || '-' || substr(received, 1, 2)
        WHEN received GLOB '[0-9][0-9]-[A-Z][a-z][a-z]-[0-9][0-9][0-9][0-9]*'
            THEN substr(received, 8, 4) || '-' || CASE substr(received, 4, 3)
                WHEN 'Jan' THEN '01' WHEN 'Feb' THEN '02' WHEN 'Mar' THEN '03' WHEN 'Apr' THEN '04'
                WHEN 'May' THEN '05' WHEN 'Jun' THEN '06' WHEN 'Jul' THEN '07' WHEN 'Aug' THEN '08'
                WHEN 'Sep' THEN '09' WHEN 'Oct' THEN '10' WHEN 'Nov' THEN '11' WHEN 'Dec' THEN '12' END
    END AS year_month,
    upper(channel) AS channel,
    CASE
        WHEN lower(type) LIKE '%pot%hole%' THEN 'pothole'
        WHEN lower(type) LIKE '%sidewalk%' THEN 'sidewalk_damage'
        WHEN lower(type) LIKE '%snow%' OR lower(type) LIKE '%ice%' THEN 'snow_removal'
        WHEN lower(type) LIKE '%dumping%' THEN 'illegal_dumping'
        WHEN lower(type) LIKE '%garbage%' OR lower(type) LIKE '%collection%' THEN 'missed_garbage'
        WHEN lower(type) LIKE '%street%light%' THEN 'streetlight_out'
        WHEN lower(type) LIKE '%signal%' OR lower(type) LIKE '%traffic%' THEN 'traffic_signal'
        WHEN lower(type) LIKE '%tree%' THEN 'fallen_tree'
        WHEN lower(type) LIKE '%park%' THEN 'park_maintenance'
        WHEN lower(type) LIKE '%graffiti%' THEN 'graffiti'
        WHEN lower(type) LIKE '%noise%' THEN 'noise_complaint'
        WHEN lower(type) LIKE '%water%' THEN 'water_leak'
    END AS category,
    type AS legacy_label,
    description,
    location
FROM raw_311_landing;

-- Q1 Data quality profile of the raw export
SELECT
    COUNT(*) AS raw_rows,
    SUM(description = '') AS blank_descriptions,
    SUM(year_month IS NULL) AS unparseable_dates,
    SUM(category IS NULL) AS unknown_labels,
    COUNT(DISTINCT legacy_label) AS distinct_legacy_labels,
    SUM(description LIKE '%@%' OR description GLOB '*[0-9][0-9][0-9]?[0-9][0-9][0-9][0-9]*') AS rows_with_contact_details
FROM v_requests;

-- Q2 Request volume by category (drives staffing and the classifier's class balance)
SELECT category, COUNT(*) AS requests,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM v_requests WHERE category IS NOT NULL), 1) AS pct
FROM v_requests WHERE category IS NOT NULL
GROUP BY category ORDER BY requests DESC;

-- Q3 Seasonality: winter (Dec-Mar) versus the rest of the year for the most seasonal categories
SELECT category,
       SUM(substr(year_month, 6, 2) IN ('12', '01', '02', '03')) AS winter_requests,
       SUM(substr(year_month, 6, 2) NOT IN ('12', '01', '02', '03')) AS other_requests
FROM v_requests
WHERE category IN ('snow_removal', 'pothole', 'park_maintenance') AND year_month IS NOT NULL
GROUP BY category;

-- Q4 Channel mix (sizes the phone workload that agents still key in)
SELECT channel, COUNT(*) AS requests,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM v_requests), 1) AS pct
FROM v_requests GROUP BY channel ORDER BY requests DESC;

-- Q5 Duplicate hotspots: same category reported at the same address 3+ times in one month
SELECT category, location, year_month, COUNT(*) AS reports
FROM v_requests
WHERE category IS NOT NULL AND year_month IS NOT NULL AND location GLOB '[0-9]*'
GROUP BY category, location, year_month
HAVING COUNT(*) >= 3
ORDER BY reports DESC, year_month LIMIT 10;

-- Q6 Label sprawl: how many different legacy spellings map to each category
SELECT category, COUNT(DISTINCT legacy_label) AS spellings, group_concat(DISTINCT legacy_label) AS examples
FROM v_requests WHERE category IS NOT NULL
GROUP BY category ORDER BY category
