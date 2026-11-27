// Shower ENTRY-curb drain clip (step-over safe: low, no proud parts on top).
// Drains water pooled on a flat granite curb, over the inner edge, down to a
// drip tip below the curb top on the shower side.
//   mode = "grooves": no fabric; sharp capillary V-grooves carry the water.
//   mode = "wick":    a 12 mm polyester/microfiber strip rides in one wide groove.
// All units mm. Made for JLC3DP MJF PA12 nylon (also fine in SLA resin or FDM PETG).

/* [Variant] */
mode = "grooves"; // ["grooves", "wick"]

/* [Fit to your curb] */
pad_depth   = 59;   // arm length from the shower-side edge; glass is 2 5/8 in (66.7 mm) in, so this stops ~7.7 mm short of it, clear of the silicone
edge_radius = 3;    // radius of the curb's inner top edge (0.5 = sharp, ~3 = eased, ~19 = full bullnose on 1.5" stone)
drop        = 32;   // leg length: 3/4 in (19 mm) slab + 13 mm, so every drip point is below the overhang (floor is 44 mm further down)

/* [Part] */
width       = 30;   // along the curb
thick       = 2.6;  // wall thickness (low so it is not felt underfoot)
cap_w       = 1.0;  // capillary groove width at the surface
cap_d       = 1.3;  // capillary groove depth (~42 deg included V)
cap_pitch   = 2.0;  // groove spacing: leaves 1.0 mm ridges and comb teeth (MJF 1 mm minimum wall)
comb_len    = 8;    // grooves mode: slots cut right through to the stone at the leading edge
wick_w      = 13;   // groove width (fits a 12 mm wick strip)
wick_d      = 1.2;  // groove depth (thin polyester/microfiber strip sits flush)
feather_len = 12;   // tapered leading edge so water runs onto the arm
feather_min = 1.0;  // thickness at the leading edge (JLC MJF minimum wall)
tip_h       = 10;   // height of the V drip tip (valley stays 3 mm below the slab)

$fn = 96;
re = max(edge_radius, 0.5);

// 2D profile in (Y across curb, Z up); curb top at Z=0, inner face at Y=0.
module path_band(r_in_off, r_out_off) {
    // band offset from the curb surface between r_in_off and r_out_off
    union() {
        translate([re, r_in_off]) square([pad_depth - re + 1, r_out_off - r_in_off]);
        translate([re, -re]) intersection() {
            difference() { circle(re + r_out_off); circle(re + r_in_off); }
            translate([-(re + r_out_off + 1), 0]) square(re + r_out_off + 1);
        }
        translate([-r_out_off, -drop - 1]) square([r_out_off - r_in_off, drop + 1 - re]);
    }
}

module body() {
    rotate([90, 0, 90]) linear_extrude(width)
        intersection() {
            path_band(0, thick);
            translate([-50, -drop]) square([pad_depth + 50, drop + 50]);
        }
}

module groove() {
    translate([(width - wick_w) / 2, 0, 0])
    rotate([90, 0, 90]) linear_extrude(wick_w)
        path_band(thick - wick_d, thick);   // stops at the surface so keepers bridge it
}

module comb_slots() {     // inlet: slots open to the granite so water enters at stone level
    span = width - 2 * 2.6;
    count = floor((span - cap_w) / cap_pitch) + 1;
    x0 = (width - (count - 1) * cap_pitch) / 2;
    for (i = [0 : count - 1])
        translate([x0 + i * cap_pitch - cap_w / 2, pad_depth - comb_len, -1]) cube([cap_w, comb_len + 1, thick + 2]);
}

module cap_grooves() {    // field of V-grooves following the path (V built from thin slabs)
    n = 6;
    span = width - 2 * 2.6;                  // keep clear of the side chamfers
    count = floor((span - cap_w) / cap_pitch) + 1;
    x0 = (width - (count - 1) * cap_pitch) / 2;
    for (i = [0 : count - 1], k = [0 : n - 1]) {
        w = cap_w * (1 - (k + 0.5) / n);
        translate([x0 + i * cap_pitch - w / 2, 0, 0]) rotate([90, 0, 90]) linear_extrude(w)
            path_band(thick - cap_d * (k + 1) / n, thick + 0.01);
    }
}
module keeper_leg(z) {   // bar over the groove on the leg
    translate([(width - wick_w) / 2 - 2.5, -thick - 1.2 + 0.01, z]) cube([wick_w + 5, 1.2, 4]);
}

module feather() {       // wedge removing the top at the leading edge
    translate([-1, pad_depth, 0]) rotate([90, 0, 90]) linear_extrude(width + 2)
        polygon([[-feather_len, thick + 2], [-feather_len, thick], [0, feather_min], [0, thick + 2]]);
    translate([-1, pad_depth, -1]) cube([width + 2, 10, thick + 5]);
}

module side_chamfers() { // 45-degree top side edges on the arm so a foot can't catch it
    c = 1.4;
    for (x = [0, width]) translate([x, re, thick]) rotate([-90, 0, 0])
        linear_extrude(pad_depth) rotate(45) square(c * 1.414, center = true);
}

module drip_tip_keep() { // V point at the bottom so drops leave from one spot
    translate([0, 200, 0]) rotate([90, 0, 0]) linear_extrude(400)
        polygon([[0, 50], [width, 50], [width, -drop + tip_h], [width / 2, -drop], [0, -drop + tip_h]]);
}

intersection() {
    difference() {
        union() {
            body();
            if (mode == "wick") {
                keeper_leg(-re - 12);
                keeper_leg(-drop + tip_h + 2);
            }
        }
        if (mode == "wick") groove();   // keepers stay proud, leaving a tunnel for the wick
        else { cap_grooves(); comb_slots(); }
        feather();
        side_chamfers();
    }
    drip_tip_keep();
}
