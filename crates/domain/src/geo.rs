//! Geographic value objects: WGS 84 points and line geometries.
//!
//! Coordinates are degrees. The API uses `{"lat", "lng"}` objects for points and GeoJSON
//! (`[lng, lat]` positions) for geometries; both are validated here. Distances between many
//! rows are computed by PostGIS; [`GeoPoint::haversine_m`] serves tests and the in-process
//! journey planner.

use std::f64::consts::PI;

use crate::error::{Violation, Violations};

/// Mean Earth radius (IUGG), in metres.
pub const EARTH_RADIUS_M: f64 = 6_371_008.8;

/// Longest distance between two points of the Earth (half a great circle), in metres.
pub const MAX_DISTANCE_M: f64 = PI * EARTH_RADIUS_M;

/// A validated WGS 84 position: finite, latitude in [-90, 90], longitude in [-180, 180].
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct GeoPoint {
    lat: f64,
    lng: f64,
}

impl GeoPoint {
    /// Validates a latitude (degrees).
    pub fn check_lat(lat: f64) -> Result<f64, Violation> {
        check_coordinate(lat, 90.0, 90)
    }

    /// Validates a longitude (degrees).
    pub fn check_lng(lng: f64) -> Result<f64, Violation> {
        check_coordinate(lng, 180.0, 180)
    }

    /// Validates both coordinates; violations are reported on `lat` and `lng`.
    pub fn parse(lat: f64, lng: f64) -> Result<Self, Violations> {
        let mut v = Violations::new();
        let lat = v.check("lat", Self::check_lat(lat));
        let lng = v.check("lng", Self::check_lng(lng));
        match (lat, lng) {
            (Some(lat), Some(lng)) => Ok(Self { lat, lng }),
            _ => Err(v),
        }
    }

    /// Wraps coordinates that were already validated (e.g. loaded from the database).
    #[must_use]
    pub const fn from_trusted(lat: f64, lng: f64) -> Self {
        Self { lat, lng }
    }

    #[must_use]
    pub const fn lat(self) -> f64 {
        self.lat
    }

    #[must_use]
    pub const fn lng(self) -> f64 {
        self.lng
    }

    /// Great-circle distance in metres on a sphere of radius [`EARTH_RADIUS_M`] (haversine).
    /// Within 0.5 % of the geodesic distance PostGIS computes on the spheroid.
    #[must_use]
    pub fn haversine_m(self, other: Self) -> f64 {
        let (phi1, phi2) = (self.lat.to_radians(), other.lat.to_radians());
        let d_phi = phi2 - phi1;
        let d_lambda = (other.lng - self.lng).to_radians();
        let a = (d_phi / 2.0).sin().powi(2)
            + phi1.cos() * phi2.cos() * (d_lambda / 2.0).sin().powi(2);
        // Rounding can push `a` slightly above 1 for antipodal points.
        2.0 * EARTH_RADIUS_M * a.sqrt().min(1.0).asin()
    }
}

fn check_coordinate(value: f64, limit: f64, bound: i64) -> Result<f64, Violation> {
    if !value.is_finite() {
        return Err(Violation::InvalidFormat);
    }
    if (-limit..=limit).contains(&value) {
        Ok(value)
    } else {
        Err(Violation::OutOfRange { min: -bound, max: bound })
    }
}

/// The geometry of a line's itinerary: 2 to 10 000 points, no two consecutive points equal.
#[derive(Debug, Clone, PartialEq)]
pub struct LineGeometry(Vec<GeoPoint>);

impl LineGeometry {
    pub const MIN_POINTS: usize = 2;
    pub const MAX_POINTS: usize = 10_000;
    /// Point problems reported at most (a broken 10 000-point payload is not echoed back).
    const MAX_REPORTED: usize = 20;

    /// Validates GeoJSON `LineString` positions (`[lng, lat]`). Violations are reported on
    /// the empty field (the count), `[i][0]` (longitude), `[i][1]` (latitude) and `[i]` (a
    /// point equal to its predecessor), to be nested under `coordinates`.
    pub fn parse(positions: &[[f64; 2]]) -> Result<Self, Violations> {
        let mut v = Violations::new();
        if !(Self::MIN_POINTS..=Self::MAX_POINTS).contains(&positions.len()) {
            v.push("", Violation::OutOfRange { min: 2, max: 10_000 });
            return Err(v);
        }
        let mut points = Vec::with_capacity(positions.len());
        for (i, &[lng, lat]) in positions.iter().enumerate() {
            if v.len() >= Self::MAX_REPORTED {
                break;
            }
            let lng = v.check_nested(&format!("[{i}][0]"), check_one(GeoPoint::check_lng(lng)));
            let lat = v.check_nested(&format!("[{i}][1]"), check_one(GeoPoint::check_lat(lat)));
            let (Some(lng), Some(lat)) = (lng, lat) else { continue };
            let point = GeoPoint { lat, lng };
            if points.last() == Some(&point) {
                v.push(format!("[{i}]"), Violation::Duplicate);
            }
            points.push(point);
        }
        if v.is_empty() { Ok(Self(points)) } else { Err(v) }
    }

    /// Wraps points that were already validated (e.g. loaded from the database).
    #[must_use]
    pub fn from_trusted(points: Vec<GeoPoint>) -> Self {
        Self(points)
    }

    #[must_use]
    pub fn points(&self) -> &[GeoPoint] {
        &self.0
    }

    /// Length along the points, in metres (haversine).
    #[must_use]
    pub fn length_m(&self) -> f64 {
        self.0.windows(2).map(|w| w[0].haversine_m(w[1])).sum()
    }
}

/// A single violation of an unnamed value, as [`Violations`] to nest.
fn check_one(result: Result<f64, Violation>) -> Result<f64, Violations> {
    result.map_err(|violation| Violations::single("", violation))
}

#[cfg(test)]
mod tests {
    use proptest::prelude::*;

    use super::*;

    fn fields(v: &Violations) -> Vec<(String, &'static str)> {
        v.iter().map(|f| (f.field.to_string(), f.violation.code())).collect()
    }

    #[test]
    fn points_are_range_checked() {
        let p = GeoPoint::parse(36.7538, 3.0588).unwrap();
        assert_eq!((p.lat(), p.lng()), (36.7538, 3.0588));
        assert!(GeoPoint::parse(-90.0, 180.0).is_ok());
        assert!(GeoPoint::parse(0.0, 0.0).is_ok(), "zero is a valid coordinate (L-49)");
        let err = GeoPoint::parse(90.5, -180.1).unwrap_err();
        let both = |code| vec![("lat".to_owned(), code), ("lng".to_owned(), code)];
        assert_eq!(fields(&err), both("out_of_range"));
        assert_eq!(
            err.iter().next().unwrap().violation,
            Violation::OutOfRange { min: -90, max: 90 }
        );
        let err = GeoPoint::parse(f64::NAN, f64::INFINITY).unwrap_err();
        assert_eq!(fields(&err), both("invalid_format"));
    }

    #[test]
    fn haversine_matches_known_distances() {
        // Algiers (Place des Martyrs) → Oran (Place du 1er Novembre): about 354 km.
        let algiers = GeoPoint::from_trusted(36.7856, 3.0603);
        let oran = GeoPoint::from_trusted(35.6987, -0.6349);
        let d = algiers.haversine_m(oran);
        assert!((350_000.0..358_000.0).contains(&d), "{d}");
        // One degree of latitude is about 111.2 km.
        let origin = GeoPoint::from_trusted(0.0, 0.0);
        let one_degree = origin.haversine_m(GeoPoint::from_trusted(1.0, 0.0));
        assert!((one_degree - 111_195.0).abs() < 10.0, "{one_degree}");
        let antipode = origin.haversine_m(GeoPoint::from_trusted(0.0, 180.0));
        assert!((antipode - MAX_DISTANCE_M).abs() < 1e-6);
    }

    #[test]
    fn geometries_need_two_to_ten_thousand_distinct_consecutive_points() {
        let line = LineGeometry::parse(&[[3.05, 36.75], [3.06, 36.76], [3.05, 36.75]]).unwrap();
        assert_eq!(line.points().len(), 3);
        assert!(line.length_m() > 2_000.0);
        assert_eq!(
            fields(&LineGeometry::parse(&[[3.05, 36.75]]).unwrap_err()),
            vec![(String::new(), "out_of_range")]
        );
        let too_many = vec![[0.0, 0.0]; LineGeometry::MAX_POINTS + 1];
        assert!(LineGeometry::parse(&too_many).is_err());
        let err = LineGeometry::parse(&[[3.0, 36.0], [3.0, 36.0], [200.0, 95.0]]).unwrap_err();
        assert_eq!(
            fields(&err),
            vec![
                ("[1]".into(), "duplicate"),
                ("[2][0]".into(), "out_of_range"),
                ("[2][1]".into(), "out_of_range"),
            ]
        );
    }

    #[test]
    fn broken_geometries_report_a_bounded_number_of_problems() {
        let broken = vec![[500.0, 500.0]; 1000];
        let err = LineGeometry::parse(&broken).unwrap_err();
        assert!(err.len() <= 21, "{}", err.len());
    }

    fn point() -> impl Strategy<Value = GeoPoint> {
        (-90.0..=90.0f64, -180.0..=180.0f64)
            .prop_map(|(lat, lng)| GeoPoint::from_trusted(lat, lng))
    }

    proptest! {
        #[test]
        fn valid_coordinates_parse_and_round_trip(
            lat in -90.0..=90.0f64,
            lng in -180.0..=180.0f64,
        ) {
            let p = GeoPoint::parse(lat, lng).unwrap();
            prop_assert_eq!((p.lat(), p.lng()), (lat, lng));
        }

        #[test]
        fn out_of_range_coordinates_are_refused(
            lat in 90.000_001..1e9f64,
            lng in 180.000_001..1e9f64,
        ) {
            prop_assert!(GeoPoint::parse(lat, 0.0).is_err());
            prop_assert!(GeoPoint::parse(-lat, 0.0).is_err());
            prop_assert!(GeoPoint::parse(0.0, lng).is_err());
            prop_assert!(GeoPoint::parse(0.0, -lng).is_err());
        }

        #[test]
        fn haversine_is_a_metric(a in point(), b in point(), c in point()) {
            let ab = a.haversine_m(b);
            prop_assert!((0.0..=MAX_DISTANCE_M + 1e-6).contains(&ab));
            prop_assert!(a.haversine_m(a).abs() < 1e-6);
            prop_assert!((ab - b.haversine_m(a)).abs() < 1e-6);
            // Triangle inequality, with a tolerance for floating-point rounding.
            prop_assert!(a.haversine_m(c) <= ab + b.haversine_m(c) + 1e-3);
        }

        #[test]
        fn geometries_keep_their_points(points in prop::collection::vec(point(), 2..50)) {
            let positions: Vec<[f64; 2]> = points.iter().map(|p| [p.lng(), p.lat()]).collect();
            let has_repeat = points.windows(2).any(|w| w[0] == w[1]);
            match LineGeometry::parse(&positions) {
                Ok(line) => {
                    prop_assert!(!has_repeat);
                    prop_assert_eq!(line.points(), points.as_slice());
                }
                Err(_) => prop_assert!(has_repeat),
            }
        }
    }
}
