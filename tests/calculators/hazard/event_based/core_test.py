# Copyright (c) 2010-2012, GEM Foundation.
#
# OpenQuake is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# OpenQuake is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with OpenQuake.  If not, see <http://www.gnu.org/licenses/>.


import getpass
import unittest
import mock
import numpy

from openquake.hazardlib import imt
from nose.plugins.attrib import attr

from openquake.engine.db import models
from openquake.engine.calculators.hazard.event_based import core
from openquake.engine.utils import stats

from tests.utils import helpers


class EventBasedHazardCalculatorTestCase(unittest.TestCase):
    """
    Tests for the core functionality of the event-based hazard calculator.
    """

    def setUp(self):
        cfg = helpers.get_data_path('event_based_hazard/job.ini')
        self.job = helpers.get_hazard_job(cfg, username=getpass.getuser())
        self.calc = core.EventBasedHazardCalculator(self.job)
        models.JobStats.objects.create(oq_job=self.job)

    def test_donot_save_trivial_gmf(self):
        gmf_set = mock.Mock()

        # setup two ground motion fields on a region made by three
        # locations. On the first two locations the values are
        # nonzero, in the third one is zero. Then, we will expect the
        # bulk inserter to add only two entries.
        gmvs = numpy.matrix([[1., 1.],
                             [1., 1.],
                             [0., 0.]])
        gmf_dict = {imt.PGA: dict(rupture_ids=[1, 2], gmvs=gmvs)}

        fake_bulk_inserter = mock.Mock()
        with helpers.patch('openquake.engine.writer.BulkInserter') as m:
            m.return_value = fake_bulk_inserter
            core._save_gmfs(
                gmf_set, gmf_dict, [mock.Mock(), mock.Mock(), mock.Mock()], 1)
            self.assertEqual(2, fake_bulk_inserter.add_entry.call_count)

    def test_save_only_nonzero_gmvs(self):
        gmf_set = mock.Mock()

        gmvs = numpy.matrix([[0.0, 0, 1]])
        gmf_dict = {imt.PGA: dict(rupture_ids=[1, 2, 3], gmvs=gmvs)}

        fake_bulk_inserter = mock.Mock()
        with helpers.patch('openquake.engine.writer.BulkInserter') as m:
            m.return_value = fake_bulk_inserter
            core._save_gmfs(
                gmf_set, gmf_dict, [mock.Mock()], 1)
            call_args = fake_bulk_inserter.add_entry.call_args_list[0][1]
            self.assertEqual([1], call_args['gmvs'])
            self.assertEqual([3], call_args['rupture_ids'])

    def test_initialize_ses_db_records(self):
        hc = self.job.hazard_calculation

        # Initialize sources as a setup for the test:
        self.calc.initialize_sources()

        self.calc.initialize_realizations(
            rlz_callbacks=[self.calc.initialize_ses_db_records])

        outputs = models.Output.objects.filter(
            oq_job=self.job, output_type='ses')
        self.assertEqual(2, len(outputs))

        # With this job configuration, we have 2 logic tree realizations.
        lt_rlzs = models.LtRealization.objects.filter(hazard_calculation=hc)
        self.assertEqual(2, len(lt_rlzs))

        for rlz in lt_rlzs:
            sess = models.SES.objects.filter(
                ses_collection__lt_realization=rlz)
            self.assertEqual(hc.ses_per_logic_tree_path, len(sess))

            for ses in sess:
                # The only metadata in in the SES is investigation time.
                self.assertEqual(hc.investigation_time, ses.investigation_time)

    def test_initialize_pr_data_with_ses(self):
        hc = self.job.hazard_calculation

        # Initialize sources as a setup for the test:
        self.calc.initialize_sources()

        self.calc.initialize_realizations(
            rlz_callbacks=[self.calc.initialize_ses_db_records])

        ltr1, ltr2 = models.LtRealization.objects.filter(
            hazard_calculation=hc).order_by("id")

        ltr1.completed_items = 12
        ltr1.save()

        self.calc.initialize_pr_data()

        total = stats.pk_get(self.calc.job.id, "nhzrd_total")
        self.assertEqual(ltr1.total_items + ltr2.total_items, total)
        done = stats.pk_get(self.calc.job.id, "nhzrd_done")
        self.assertEqual(ltr1.completed_items + ltr2.completed_items, done)

    def test_initialize_gmf_db_records(self):
        hc = self.job.hazard_calculation

        # Initialize sources as a setup for the test:
        self.calc.initialize_sources()

        self.calc.initialize_realizations(
            rlz_callbacks=[self.calc.initialize_gmf_db_records])

        outputs = models.Output.objects.filter(
            oq_job=self.job, output_type='gmf')
        self.assertEqual(2, len(outputs))

        lt_rlzs = models.LtRealization.objects.filter(hazard_calculation=hc)
        self.assertEqual(2, len(lt_rlzs))

        for rlz in lt_rlzs:
            gmf_sets = models.GmfSet.objects.filter(
                gmf_collection__lt_realization=rlz)
            self.assertEqual(hc.ses_per_logic_tree_path, len(gmf_sets))

            for gmf_set in gmf_sets:
                # The only metadata in a GmfSet is investigation time.
                self.assertEqual(
                    hc.investigation_time, gmf_set.investigation_time)

    def test_initialize_pr_data_with_gmf(self):
        hc = self.job.hazard_calculation

        # Initialize sources as a setup for the test:
        self.calc.initialize_sources()

        self.calc.initialize_realizations(
            rlz_callbacks=[self.calc.initialize_gmf_db_records])

        ltr1, ltr2 = models.LtRealization.objects.filter(
            hazard_calculation=hc).order_by("id")

        ltr1.completed_items = 13
        ltr1.save()

        self.calc.initialize_pr_data()

        total = stats.pk_get(self.calc.job.id, "nhzrd_total")
        self.assertEqual(ltr1.total_items + ltr2.total_items, total)
        done = stats.pk_get(self.calc.job.id, "nhzrd_done")
        self.assertEqual(ltr1.completed_items + ltr2.completed_items, done)

    def test_initialize_complete_lt_ses_db_records_branch_enum(self):
        # Set hazard_calculation.number_of_logic_tree_samples = 0
        # This indicates that the `end-branch enumeration` method should be
        # used to carry out the calculation.

        # This test was added primarily for branch coverage (in the case of end
        # branch enum) for the method `initialize_complete_lt_ses_db_records`.
        hc = self.job.hazard_calculation
        hc.number_of_logic_tree_samples = 0

        self.calc.initialize_sources()
        self.calc.initialize_realizations()

        self.calc.initialize_complete_lt_ses_db_records()

        complete_lt_ses = models.SES.objects.get(
            ses_collection__output__oq_job=self.job.id,
            ses_collection__output__output_type='complete_lt_ses',
            ordinal=None)

        self.assertEqual(250.0, complete_lt_ses.investigation_time)
        self.assertIsNone(complete_lt_ses.ordinal)

    # TODO(LB): This test is becoming a bit epic. Once QA test data is
    # we can probably refactor or replace this test.
    @attr('slow')
    def test_complete_event_based_calculation_cycle(self):
        # Run the entire calculation cycle and check that outputs are created

        cfg = helpers.get_data_path('event_based_hazard/job.ini')
        job = helpers.run_hazard_job(cfg)

        hc = job.hazard_calculation

        rlz1, rlz2 = models.LtRealization.objects.filter(
            hazard_calculation=hc.id).order_by('ordinal')

        # Now check that we saved the right number of ruptures to the DB.
        ruptures1 = models.SESRupture.objects.filter(
            ses__ses_collection__lt_realization=rlz1)
        self.assertEqual(104, ruptures1.count())

        ruptures2 = models.SESRupture.objects.filter(
            ses__ses_collection__lt_realization=rlz2)
        self.assertEqual(117, ruptures2.count())

        # Check that we have the right number of gmf_sets.
        # The correct number is (num_realizations * ses_per_logic_tree_path).
        gmf_sets = models.GmfSet.objects.filter(
            gmf_collection__output__oq_job=job.id,
            gmf_collection__lt_realization__isnull=False)
        # 2 realizations, 5 ses_per_logic_tree_path
        self.assertEqual(10, gmf_sets.count())

        for imt in hc.intensity_measure_types:
            imt, sa_period, sa_damping = models.parse_imt(imt)
            # Now check that we have the right number of GMFs in the DB.

            # The expected number of `Gmf` records per IMT is
            # num_sites * ses_per_logic_tree_path * num_tasks
            # num tasks should be 8 (2 LT realizations * 4 sources, with 1
            # source per task)
            # Thus:
            # (121 * 5 * (2 * 4) = 4840
            gmfs = models.Gmf.objects.filter(
                gmf_set__gmf_collection__output__oq_job=job,
                imt=imt, sa_period=sa_period, sa_damping=sa_damping
            )
            self.assertEqual(4840, gmfs.count())

        # Check the complete logic tree SES and make sure it contains
        # all of the ruptures.
        complete_lt_ses = models.SES.objects.get(
            ses_collection__output__oq_job=job.id,
            ses_collection__output__output_type='complete_lt_ses',
            ordinal=None)

        clt_ses_ruptures = models.SESRupture.objects.filter(
            ses=complete_lt_ses.id)

        self.assertEqual(221, clt_ses_ruptures.count())

        # Test the computed `investigation_time`
        # 2 lt realizations * 5 ses_per_logic_tree_path * 50.0 years
        self.assertEqual(500.0, complete_lt_ses.investigation_time)

        self.assertIsNone(complete_lt_ses.ordinal)

        # Now check for the correct number of hazard curves:
        curves = models.HazardCurve.objects.filter(output__oq_job=job)
        # ((2 IMTs * 2 realizations) + (2 IMTs * (1 mean + 2 quantiles))) = 10
        self.assertEqual(10, curves.count())

        # Finally, check for the correct number of hazard maps:
        maps = models.HazardMap.objects.filter(output__oq_job=job)
        # ((2 poes * 2 realizations * 2 IMTs)
        # + (2 poes * 2 IMTs * (1 mean + 2 quantiles))) = 20
        self.assertEqual(20, maps.count())