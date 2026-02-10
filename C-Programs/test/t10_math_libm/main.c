#include "mathutil.h"

int main(void) {
    printf("=== t10_math_libm ===\n\n");

    /* --- Trigonometry --- */
    printf("--- trig ---\n");
    double angles[] = {0, 30, 45, 60, 90, 180, 270, 360};
    int na = sizeof(angles) / sizeof(angles[0]);
    for (int i = 0; i < na; i++) {
        double r = deg_to_rad(angles[i]);
        printf("  %6.1f deg => sin=%.6f  cos=%.6f\n",
               angles[i], sin(r), cos(r));
    }

    printf("\n  triangle_area(3, 4, 90deg) = %.4f\n",
           triangle_area(3.0, 4.0, deg_to_rad(90.0)));
    printf("  triangle_area(5, 7, 45deg) = %.4f\n",
           triangle_area(5.0, 7.0, deg_to_rad(45.0)));

    /* Sincos table */
    double sout[37], cout[37];
    int cnt;
    sincos_table(0, 360, 30, sout, cout, &cnt, 37);
    printf("\n  sincos table (%d entries):\n", cnt);
    for (int i = 0; i < cnt; i++)
        printf("    [%2d] sin=% .4f  cos=% .4f\n", i, sout[i], cout[i]);

    /* Wave sum */
    printf("\n  wave_sum(1.0, harmonics):\n");
    for (int h = 1; h <= 8; h++)
        printf("    h=%d => %.6f\n", h, wave_sum(1.0, h));

    /* --- Statistics --- */
    printf("\n--- stats ---\n");
    double data[] = {2.5, 3.7, 1.2, 4.8, 5.1, 3.3, 2.9, 4.0};
    int nd = sizeof(data) / sizeof(data[0]);

    printf("  data: ");
    for (int i = 0; i < nd; i++) printf("%.1f ", data[i]);
    printf("\n");

    printf("  mean     = %.6f\n", mean(data, nd));
    printf("  variance = %.6f\n", variance(data, nd));
    printf("  stddev   = %.6f\n", stddev(data, nd));
    printf("  rms      = %.6f\n", rms(data, nd));
    printf("  geo_mean = %.6f\n", geometric_mean(data, nd));

    /* Angle normalization */
    printf("\n--- angle normalization ---\n");
    double test_rads[] = {0.0, PI, -PI, 3*PI, -5.0, 10.0, 100.0};
    int nt = sizeof(test_rads) / sizeof(test_rads[0]);
    for (int i = 0; i < nt; i++) {
        printf("  normalize(%.4f) = %.4f  (%.1f deg)\n",
               test_rads[i],
               normalize_angle(test_rads[i]),
               rad_to_deg(normalize_angle(test_rads[i])));
    }

    printf("\nDone.\n");
    return 0;
}
