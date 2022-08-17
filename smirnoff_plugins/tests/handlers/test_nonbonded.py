import pytest
from openff.toolkit.topology import Molecule, Topology
from openff.toolkit.typing.engines.smirnoff import ForceField
from simtk import openmm, unit

from smirnoff_plugins.utilities.openmm import (
    evaluate_energy,
    evaluate_water_energy_at_distances,
)


@pytest.mark.parametrize(
    "switch_width, use_switch",
    [
        pytest.param(1 * unit.angstroms, True, id="Switch on"),
        pytest.param(0 * unit.angstroms, False, id="Switch off"),
    ],
)
def test_use_switch_width(
    water_box_topology, buckingham_water_force_field, switch_width, use_switch
):
    """Make sure the switch width is respected when requested"""

    buckingham_handler = buckingham_water_force_field.get_parameter_handler(
        "DampedBuckingham68"
    )
    buckingham_handler.switch_width = switch_width
    system = buckingham_water_force_field.create_openmm_system(water_box_topology)
    for i in range(system.getNumForces()):
        force = system.getForce(i)
        if isinstance(force, openmm.CustomNonbondedForce):
            custom_force = force
            break
    assert custom_force.getUseSwitchingFunction() is use_switch


def test_switch_width(water_box_topology, buckingham_water_force_field):
    """Make sure the switch width is respected when set."""

    buckingham_handler = buckingham_water_force_field.get_parameter_handler(
        "DampedBuckingham68"
    )
    buckingham_handler.switch_width = 1.0 * unit.angstroms
    buckingham_handler.cutoff = 8.5 * unit.angstroms

    system = buckingham_water_force_field.create_openmm_system(water_box_topology)
    for i in range(system.getNumForces()):
        force = system.getForce(i)
        if isinstance(force, openmm.CustomNonbondedForce):
            custom_force = force
            break

    # make sure it has been adjusted
    assert custom_force.getSwitchingDistance() == 7.5 * unit.angstroms


def test_double_exp_energies(ideal_water_force_field):
    """
    Make sure that energies computed using OpenMM match reference values calculated by hand for two O atoms in water at set distances.
    """
    epsilon = 0.152  # kcal/mol
    r_min = 3.5366  # angstrom
    alpha = 18.7
    beta = 3.3

    # Add the DE block
    double_exp = ideal_water_force_field.get_parameter_handler("DoubleExponential")
    double_exp.alpha = alpha
    double_exp.beta = beta
    double_exp.scale14 = 1
    double_exp.add_parameter(
        {
            "smirks": "[#1]-[#8X2H2+0:1]-[#1]",
            "r_min": r_min * unit.angstrom,
            "epsilon": epsilon * unit.kilocalorie_per_mole,
        }
    )
    double_exp.add_parameter(
        {
            "smirks": "[#1:1]-[#8X2H2+0]-[#1]",
            "r_min": 1 * unit.angstrom,
            "epsilon": 0 * unit.kilocalorie_per_mole,
        }
    )

    energies = evaluate_water_energy_at_distances(
        force_field=ideal_water_force_field, distances=[2, r_min, 4]
    )
    # calculated by hand (kJ / mol), at r_min the energy should be epsilon
    ref_values = [457.0334854, -0.635968, -0.4893932627]
    for i, energy in enumerate(energies):
        assert energy == pytest.approx(ref_values[i])


def test_b68_energies(ideal_water_force_field):
    """Make sure that energies calculated using OpenMM match reference values calculated by hand for two O atoms in water at set distances"""

    # build the force field with no charges
    gamma = 35.8967
    a = 1600000.0
    b = 42
    c6 = 0.003
    c8 = 0.00003

    # add the b68 block
    buckingham_handler = ideal_water_force_field.get_parameter_handler(
        "DampedBuckingham68"
    )
    buckingham_handler.gamma = gamma * unit.nanometer**-1
    buckingham_handler.add_parameter(
        {
            "smirks": "[#1:1]-[#8X2H2+0]-[#1]",
            "a": 0.0 * unit.kilojoule_per_mole,
            "b": 0.0 / unit.nanometer,
            "c6": 0.0 * unit.kilojoule_per_mole * unit.nanometer**6,
            "c8": 0.0 * unit.kilojoule_per_mole * unit.nanometer**8,
        }
    )
    buckingham_handler.add_parameter(
        {
            "smirks": "[#1]-[#8X2H2+0:1]-[#1]",
            "a": a * unit.kilojoule_per_mole,
            "b": b / unit.nanometer,
            "c6": c6 * unit.kilojoule_per_mole * unit.nanometer**6,
            "c8": c8 * unit.kilojoule_per_mole * unit.nanometer**8,
        }
    )

    energies = evaluate_water_energy_at_distances(
        force_field=ideal_water_force_field, distances=[2, 3, 4]
    )
    # calculated by hand (kJ / mol)
    ref_values = [329.305, 1.303183, -0.686559]
    for i, energy in enumerate(energies):
        assert energy == pytest.approx(ref_values[i])


def test_scaled_de_energy():
    """For a molecule with 1-4 interactions make sure the scaling is correctly applied.
    Note that only nonbonded parameters are non zero.
    """

    ff = ForceField(load_plugins=True)
    ff.get_parameter_handler("Electrostatics")

    ff.get_parameter_handler(
        "ChargeIncrementModel",
        {"version": "0.3", "partial_charge_method": "formal_charge"},
    )
    vdw_handler = ff.get_parameter_handler("vdW")
    vdw_handler.add_parameter(
        {
            "smirks": "[*:1]",
            "epsilon": 0.0 * unit.kilojoule_per_mole,
            "sigma": 1.0 * unit.angstrom,
        }
    )
    double_exp = ff.get_parameter_handler("DoubleExponential")
    double_exp.alpha = 18.7
    double_exp.beta = 3.3
    double_exp.scale14 = 1
    double_exp.add_parameter(
        {
            "smirks": "[#6X4:1]",
            "r_min": 3.816 * unit.angstrom,
            "epsilon": 0.1094 * unit.kilocalorie_per_mole,
        }
    )
    double_exp.add_parameter(
        {
            "smirks": "[#1:1]-[#6X4]",
            "r_min": 2.974 * unit.angstrom,
            "epsilon": 0.0157 * unit.kilocalorie_per_mole,
        }
    )

    ethane = Molecule.from_smiles("CC")
    ethane.generate_conformers(n_conformers=1)
    off_top = ethane.to_topology()
    omm_top = off_top.to_openmm()
    system_no_scale = ff.create_openmm_system(topology=off_top)
    energy_no_scale = evaluate_energy(
        system=system_no_scale, topology=omm_top, positions=ethane.conformers[0]
    )
    # now scale 1-4 by half
    double_exp.scale14 = 0.5
    system_scaled = ff.create_openmm_system(topology=off_top)
    energy_scaled = evaluate_energy(
        system=system_scaled, topology=omm_top, positions=ethane.conformers[0]
    )
    assert double_exp.scale14 * energy_no_scale == pytest.approx(
        energy_scaled, abs=1e-6
    )


# TODO: Test that an error is raised if the MultipoleHandler encounters a vsite in the topology


def test_multipole_basic():
    """
    <SMIRNOFF version="0.3" aromaticity_model="OEAroModel_MDL">
    <Author>Adam Hogan</Author>
    <Date>2022-07-03</Date>
    <Multipole version="0.3" polarizationType="Extrapolated" cutoff="9.0 * angstrom">
    <Atom smirks="[#1:1]" polarity="0.301856 * angstrom**3"></Atom> <!-- H -->
    <Atom smirks="[#6:1]" polarity="1.243042 * angstrom**3"></Atom> <!-- C -->
    """
    toluene = Molecule.from_mapped_smiles(
        "[H:10][c:3]1[c:2]([c:1]([c:6]([c:5]([c:4]1[H:11])[H:12])[C:7]([H:13])([H:14])[H:15])[H:8])[H:9]"
    )
    ff = ForceField(load_plugins=True)
    ff.get_parameter_handler("ToolkitAM1BCC")
    mph = ff.get_parameter_handler("Multipole")
    mph.add_parameter({"smirks": "[#1:1]", "polarity": "0.301856 * angstrom**3"})
    mph.add_parameter({"smirks": "[#6:1]", "polarity": "1.243042 * angstrom**3"})

    top = Topology.from_molecules([toluene] * 2)
    sys = ff.create_openmm_system(top)

    amoeba_forces = [
        sys.getForce(i)
        for i in range(sys.getNumForces())
        if isinstance(sys.getForce(i), openmm.AmoebaMultipoleForce)
    ]
    assert len(amoeba_forces) == 1
    amoeba_force = amoeba_forces[0]
    assert amoeba_force.getNumMultipoles() == 30
    c_polarity = 1.243042 * unit.angstrom**3
    h_polarity = 0.301856 * unit.angstrom**3
    expected_polarities = (
        [c_polarity] * 7 + [h_polarity] * 8 + [c_polarity] * 7 + [h_polarity] * 8
    )
    for particle_idx in range(amoeba_force.getNumMultipoles()):
        multipole_parameters = amoeba_force.getMultipoleParameters(particle_idx)
        expected_polarity = expected_polarities[particle_idx].value_in_unit(
            unit.angstrom**3
        )
        assigned_polarity = multipole_parameters[-1].value_in_unit(unit.angstrom**3)
        assert assigned_polarity == expected_polarity
        for degree, omm_kw in [
            (1, amoeba_force.Covalent12),
            (2, amoeba_force.Covalent13),
            (3, amoeba_force.Covalent14),
        ]:
            amoeba_neighs = amoeba_force.getCovalentMap(particle_idx, omm_kw)
            molecule_neighs = []
            for pair in top.nth_degree_neighbors(degree):
                if pair[0].topology_atom_index == particle_idx:
                    molecule_neighs.append(pair[1].topology_atom_index)
                if pair[1].topology_atom_index == particle_idx:
                    molecule_neighs.append(pair[0].topology_atom_index)
            assert set(amoeba_neighs) == set(molecule_neighs)


def test_dampedexp6810():
    """
    <SMIRNOFF version="0.3" aromaticity_model="OEAroModel_MDL">
    <Author>Adam Hogan</Author>
    <Date>2022-07-03</Date>
    <DampedExp6810 version="0.3" cutoff="9.0 * angstrom">
    <Atom smirks="[#1:1]" sigma="2.097458 * angstrom" beta="3.967801 * angstrom**-1"
        c6="1.101211e-04 * kilojoule_per_mole * nanometer**6" c8="0.000000e+00 * kilojoule_per_mole * nanometer**8"
        c10="0.000000e+00 * kilojoule_per_mole * nanometer**10"></Atom> <!-- H -->
    <Atom smirks="[#6:1]" sigma="3.476471 * angstrom" beta="3.247751 * angstrom**-1"
        c6="1.617447e-03 * kilojoule_per_mole * nanometer**6" c8="1.394968e-04 * kilojoule_per_mole * nanometer**8"
        c10="1.473786e-05 * kilojoule_per_mole * nanometer**10"></Atom> <!-- C -->
    """
    toluene = Molecule.from_mapped_smiles(
        "[H:10][c:3]1[c:2]([c:1]([c:6]([c:5]([c:4]1[H:11])[H:12])[C:7]([H:13])([H:14])[H:15])[H:8])[H:9]"
    )
    ff = ForceField(load_plugins=True)
    ff.get_parameter_handler("ToolkitAM1BCC")
    handler = ff.get_parameter_handler("DampedExp6810")
    handler.add_parameter(
        {
            "smirks": "[#1:1]",
            "sigma": "2.097458 * angstrom",
            "beta": "3.967801 * angstrom**-1",
            "c6": "1.101211e-04 * kilojoule_per_mole * nanometer**6",
            "c8": "0.000000e+00 * kilojoule_per_mole * nanometer**8",
            "c10": "0.000000e+00 * kilojoule_per_mole * nanometer**10",
        }
    )
    handler.add_parameter(
        {
            "smirks": "[#6:1]",
            "sigma": "3.476471 * angstrom",
            "beta": "3.247751 * angstrom**-1",
            "c6": "1.617447e-03 * kilojoule_per_mole * nanometer**6",
            "c8": "1.394968e-04 * kilojoule_per_mole * nanometer**8",
            "c10": "1.473786e-05 * kilojoule_per_mole * nanometer**10",
        }
    )

    top = Topology.from_molecules([toluene])
    sys = ff.create_openmm_system(top)

    custom_nonbonded_forces = [
        sys.getForce(i)
        for i in range(sys.getNumForces())
        if isinstance(sys.getForce(i), openmm.CustomNonbondedForce)
    ]

    assert len(custom_nonbonded_forces) == 1

    force = custom_nonbonded_forces[0]

    assert force.getNumParticles() == 15

    expected_sigmas = [3.476471 * unit.angstrom] * 7 + [2.097458 * unit.angstrom] * 8
    expected_betas = [3.247751 * unit.angstrom**-1] * 7 + [
        3.967801 * unit.angstrom**-1
    ] * 8
    expected_c6s = [
        1.617447e-03 * unit.kilojoule_per_mole * unit.nanometer**6
    ] * 7 + [1.101211e-04 * unit.kilojoule_per_mole * unit.nanometer**6] * 8
    expected_c8s = [
        1.394968e-04 * unit.kilojoule_per_mole * unit.nanometer**8
    ] * 7 + [0.000000e00 * unit.kilojoule_per_mole * unit.nanometer**8] * 8
    expected_c10s = [
        1.473786e-05 * unit.kilojoule_per_mole * unit.nanometer**10
    ] * 7 + [0.000000e00 * unit.kilojoule_per_mole * unit.nanometer**10] * 8

    for particle_idx in range(force.getNumParticles()):
        params = force.getParticleParameters(particle_idx)
        assigned_sigma = params[0]
        expected_sigma = expected_sigmas[particle_idx].value_in_unit(unit.nanometers)
        assigned_beta = params[1]
        expected_beta = expected_betas[particle_idx].value_in_unit(
            unit.nanometers**-1
        )
        assigned_c6 = params[2]
        expected_c6 = expected_c6s[particle_idx].value_in_unit(
            unit.kilojoule_per_mole * unit.nanometer**6
        )
        assigned_c8 = params[3]
        expected_c8 = expected_c8s[particle_idx].value_in_unit(
            unit.kilojoule_per_mole * unit.nanometer**8
        )
        assigned_c10 = params[4]
        expected_c10 = expected_c10s[particle_idx].value_in_unit(
            unit.kilojoule_per_mole * unit.nanometer**10
        )

        assert assigned_sigma == expected_sigma
        assert assigned_beta == expected_beta
        assert assigned_c6 == expected_c6
        assert assigned_c8 == expected_c8
        assert assigned_c10 == expected_c10
