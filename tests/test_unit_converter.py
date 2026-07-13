import unittest

from server.tools.unit_converter import convert, horsepower_reference


class UnitConverterTests(unittest.TestCase):
    def test_kw_cp_ps_metric_horsepower(self):
        self.assertAlmostEqual(convert(1, "CP", "kW").value, 0.73549875, places=8)
        self.assertAlmostEqual(convert(1, "PS", "kW").value, 0.73549875, places=8)
        self.assertAlmostEqual(convert(1, "kW", "CP").value, 1.3596216, places=7)
        self.assertAlmostEqual(convert(1, "kW", "PS").value, 1.3596216, places=7)

    def test_kw_hp_mechanical_horsepower(self):
        self.assertAlmostEqual(convert(1, "hp", "kW").value, 0.74569987, places=8)
        self.assertAlmostEqual(convert(1, "kW", "hp").value, 1.3410221, places=7)

    def test_temperature(self):
        self.assertAlmostEqual(convert(0, "C", "F").value, 32.0, places=6)
        self.assertAlmostEqual(convert(0, "C", "K").value, 273.15, places=6)

    def test_pressure(self):
        self.assertAlmostEqual(convert(1, "bar", "Pa").value, 100000.0, places=6)
        self.assertAlmostEqual(convert(100000, "Pa", "bar").value, 1.0, places=6)

    def test_energy(self):
        self.assertAlmostEqual(convert(1, "kWh", "J").value, 3_600_000.0, places=6)
        self.assertAlmostEqual(convert(3_600_000, "J", "kWh").value, 1.0, places=6)

    def test_speed(self):
        self.assertAlmostEqual(convert(36, "km/h", "m/s").value, 10.0, places=6)
        self.assertAlmostEqual(convert(10, "m/s", "km/h").value, 36.0, places=6)

    def test_reference_constants(self):
        ref = horsepower_reference()
        self.assertAlmostEqual(ref["metric_hp_kw"], 0.73549875, places=8)
        self.assertAlmostEqual(ref["mechanical_hp_kw"], 0.74569987, places=8)


if __name__ == "__main__":
    unittest.main()
