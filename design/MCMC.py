import os
import random
import numpy as np
import sys
sys.path.append('../')
from design import Constraints


class ProteinDesign:
    """
    Optimizes a protein sequence based on a custom energy function. Set weights of constraints to 0 which you don't want to use.

    Parameters:
        native_seq (str): native sequence to be optimized
        constraints (dict): constraints on sequence. Keys describe the kind of constraint and values the position on which they act.
        sampler (str): choose between simulated_annealing and substitution design. Default simulated annealing
        n_traj (int): number of independent trajectories.
        steps (int): number of sampling steps per trajectory. For simulated annealing, the number of iterations is often chosen in the range of [1,000, 10,000].
        mut_p (tuple): probabilities for substitution, insertion and deletion. Default [0.6, 0.2, 0.2]
        T (float): sampling temperature. For simulated annealing, T0 is often chosen in the range [1, 100]. default 10
        M (float): rate of temperature decay. or simulated annealing, a is often chosen in the range [0.01, 0.1] or [0.001, 0.01]. Default 0.01
        max_len (int): maximum length sequence length for lenght constraint
        w_len (float): weight of length constraint
        w_identity (float): Weight of sequence identity constraint. Positive values reward low sequence identity to native sequence.
        pred_struc (bool): if True predict the structure of the protein at every step and use structure based constraints in the energy function. Default True.
        w_ptm (float): weight for ptm. Default 0.4
        w_plddt (float): weight for plddt. Default 0.4
        w_globularity (float): weight of globularity constraint
        w_bb_coord (float): weight on backbone constraint. Constraints backbone to native structure.
        w_sasa (float): weight of surface exposed hydrophobics constraint
        outdir (str): path to output directory. Default None
        verbose (bool): if verbose print information
    """

    def __init__(self, native_seq: str = None, constraints: dict = {'no_mut':[], 'all_atm':[]},
                 sampler: str = 'simulated_annealing',
                 n_traj: int = 5, steps: int = 1000,
                 mut_p: tuple = (0.6, 0.2, 0.2),
                 T: float = 10., M: float = 0.01,
                 max_len = 200, w_len=0.2,
                 pred_struc: bool = True,
                 w_ptm: float = 0.2, w_plddt: float = 0.2,
                 w_identity = 0.2,
                 w_globularity: float = 0.002,
                 w_bb_coord: float = 0.02,
                 w_all_atm: float = 0.02,
                 w_sasa: float = 0.02,
                 outdir = None,
                 verbose = False,
                 ):

        self.native_seq = native_seq
        self.sampler = sampler
        self.n_traj = n_traj
        self.steps = steps
        self.mut_p = mut_p
        self.T = T
        self.M = M
        self.pred_struc = pred_struc
        self.max_len = max_len
        self.w_max_len = w_len
        self.w_identity = w_identity
        self.w_ptm = w_ptm
        self.w_plddt = w_plddt
        self.w_globularity = w_globularity
        self.outdir = outdir
        self.verbose = verbose
        self.constraints = constraints
        self.w_sasa = w_sasa
        self.w_bb_coord = w_bb_coord
        self.w_all_atm = w_all_atm
        self.ref_pdbs = None


    def __str__(self):
        l = ['ProteusAI.MCMC.Hallucination class: \n',
             '---------------------------------------\n',
             'When Hallucination.run() sequences will be hallucinated using this seed sequence:\n\n',
             f'{self.native_seq}\n',
             '\nThe following variables were set:\n\n',
             'variable\t|value\n',
             '----------------+-------------------\n',
             f'algorithm: \t|{self.sampler}\n',
             f'steps: \t\t|{self.steps}\n',
             f'n_traj: \t|{self.n_traj}\n',
             f'mut_p: \t\t|{self.mut_p}\n',
             f'T: \t\t|{self.T}\n',
             f'M: \t\t|{self.M}\n\n',
             f'The energy function is a linear combination of the following constraints:\n\n',
             f'constraint\t|value\t|weight\n',
             '----------------+-------+------------\n',
             f'length \t\t|{self.max_len}\t|{self.w_max_len}\n',
             f'identity\t|\t|{self.w_identity}\n',
             ]
        s = ''.join(l)
        if self.pred_struc:
            l = [
                s,
                f'pTM\t\t|\t|{self.w_ptm}\n',
                f'pLDDT\t\t|\t|{self.w_plddt}\n',
                f'sasa\t\t|\t|{self.w_sasa}\n',
            ]
            s = ''.join(l)
        return s

    ### SAMPLERS
    def mutate(self, seqs, mut_p: tuple = (0.6, 0.2, 0.2), constraints=None):
        """
        mutates input sequences.

        Parameters:
            seqs (tuple): list of peptide sequences
            mut_p (tuple): mutation probabilities
            constraints (dict): dictionary of constraints

        Returns:
            list: mutated sequences
        """

        AAs = ('A', 'C', 'D', 'E', 'F', 'G', 'H',
               'I', 'K', 'L', 'M', 'N', 'P', 'Q',
               'R', 'S', 'T', 'V', 'W', 'Y')

        mut_types = ('substitution', 'insertion', 'deletion')

        mutated_seqs = []
        mutated_constraints = []
        for i, seq in enumerate(seqs):
            mut_constraints = {}

            # loop until allowed mutation has been selected
            mutate = True
            while mutate:
                pos = random.randint(0, len(seq) - 1)
                mut_type = random.choices(mut_types, mut_p)[0]
                if pos in constraints[i]['no_mut'] or pos in constraints[i]['all_atm']:
                    pass
                # secondary structure constraint disallows deletion
                # insertions between two secondary structure constraints will have the constraint of their neighbors
                else:
                    break

            if mut_type == 'substitution':
                with open('test', 'w') as f:
                    print(mut_type, file=f)
                replacement = random.choice(AAs)
                mut_seq = ''.join([seq[:pos], replacement, seq[pos + 1:]])
                for const in constraints[i].keys():
                    positions = constraints[i][const]
                    mut_constraints[const] = positions

            elif mut_type == 'insertion':
                with open('test', 'w') as f:
                    print(mut_type, file=f)
                insertion = random.choice(AAs)
                mut_seq = ''.join([seq[:pos], insertion, seq[pos:]])
                # shift constraints after insertion
                for const in constraints[i].keys():
                    positions = constraints[i][const]
                    positions = [i if i < pos else i + 1 for i in positions]
                    mut_constraints[const] = positions

            elif mut_type == 'deletion' and len(seq) > 1:
                with open('test', 'w') as f:
                    print(mut_type, file=f)
                l = list(seq)
                del l[pos]
                mut_seq = ''.join(l)
                # shift constraints after deletion
                for const in constraints[i].keys():
                    positions = constraints[i][const]
                    positions = [i if i < pos else i - 1 for i in positions]
                    mut_constraints[const] = positions

            else:
                with open('test', 'w') as f:
                    print('else', file=f)
                # will perform insertion if length is to small
                insertion = random.choice(AAs)
                mut_seq = ''.join([seq[:pos], insertion, seq[pos:]])
                # shift constraints after insertion
                for const in constraints[i].keys():
                    positions = constraints[i][const]
                    positions = [i if i < pos else i + 1 for i in positions]
                    mut_constraints[const] = positions

            mutated_seqs.append(mut_seq)
            mutated_constraints.append(mut_constraints)
            with open('mutations', 'w') as f:
                print('mutation:', mut_type, '\n', 'pos:', pos, '\n', 'original constraints:', constraints, '\n', 'mutated constraints:', mutated_constraints,'sequence:', mut_seq, file=f)

        return mutated_seqs, mutated_constraints

    ### ENERGY FUNCTION and ACCEPTANCE CRITERION
    def energy_function(self, seqs: list, i, consts: list):
        """
        Combines constraints into an energy function.

        Parameters:
            seqs (list): list of sequences

        Returns:
            list: Energy value
        """
        # reinitialize energy
        energies = np.zeros(len(seqs))

        e_len = self.w_max_len * Constraints.length_constraint(seqs=seqs, max_len=self.max_len)
        e_identity = self.w_identity * Constraints.seq_identity(seqs=seqs, ref=self.native_seq)
        energies += e_len
        energies +=  e_identity

        pdbs = []
        if self.pred_struc:
            names = [f'sequence_{j}_cycle_{i}' for j in range(len(seqs))]
            headers, sequences, pdbs, pTMs, pLDDTs = Constraints.structure_prediction(seqs, names)
            pTMs = [1 - val for val in pTMs]
            pLDDTs = [1 - val / 100 for val in pLDDTs]
            energies += self.w_ptm * np.array(pTMs)
            energies += self.w_plddt * np.array(pLDDTs)
            energies += self.w_globularity * Constraints.globularity(pdbs)
            energies += self.w_sasa * Constraints.surface_exposed_hydrophobics(pdbs)

            # there are now ref pdbs before the first calculation
            if self.ref_pdbs != None:
                energies += self.w_bb_coord * Constraints.backbone_coordination(pdbs, self.ref_pdbs)
                energies += self.w_all_atm * Constraints.all_atom_coordination(pdbs, self.ref_pdbs, consts, self.ref_constraints)

            # just a line to peak into some of the progress
            with open('peak', 'w') as f:
                for i in range(len(seqs)):
                    line = [
                        'header:', '\n',
                        headers[i], '\n',
                        'sequence:\n',
                        sequences[i], '\n',
                        'pTMs:', str(pTMs[i]), '\n',
                        'pLDDT:', str(pLDDTs[i]), '\n',
                        'energy:', str(energies[i]), '\n'
                    ]
                    f.writelines(line)

        return energies, pdbs

    def p_accept(self, E_x_mut, E_x_i, T, i, M):
        """
        Decides to accep or reject changes.
        """
        T = T / (1 + M * i)
        dE = E_x_i - E_x_mut
        exp_val = np.exp(1 / (T * dE))
        p_accept = np.minimum(exp_val, np.ones_like(exp_val))
        return p_accept

    ### RUN
    def run(self):
        """
        Runs MCMC-sampling based on user defined inputs. Returns optimized sequences.
        """
        native_seq = self.native_seq
        constraints = self.constraints
        n_traj = self.n_traj
        steps = self.steps
        sampler = self.sampler
        energy_function = self.energy_function
        T = self.T
        M = self.M
        p_accept = self.p_accept
        mut_p = self.mut_p
        outdir = self.outdir

        if outdir != None:
            if not os.path.exists(outdir):
                os.mkdir(outdir)

        if sampler == 'simulated_annealing':
            mutate = self.mutate

        if native_seq is None:
            raise 'The optimizer needs a sequence to run. Define a sequence by calling SequenceOptimizer(native_seq = <your_sequence>)'

        seqs = [native_seq for _ in range(n_traj)]
        constraints = [constraints for _ in range(n_traj)]
        self.ref_constraints = constraints.copy()
        with open('constraints', 'w') as f:
            print(constraints, file=f)

        # calculation of initial state
        E_x_i, pdbs = energy_function(seqs, 0, constraints)

        self.initial_enery = E_x_i
        self.ref_pdbs = pdbs

        for i in range(steps):
            mut_seqs, constraints = mutate(seqs, mut_p, constraints)

            E_x_mut, pdbs_mut = energy_function(mut_seqs, i, constraints)
            # accept or reject change
            p = p_accept(E_x_mut, E_x_i, T, i, M)
            num = '{:04d}'.format(i)
            for n in range(len(p)):
                if p[n] > random.random():
                    E_x_i[n] = E_x_mut[n]
                    seqs[n] = mut_seqs[n]
                    if self.pred_struc and outdir != None:
                        pdbs[n] = pdbs_mut[n]
                        pdbs[n].write(os.path.join(outdir, f'{num}_design_{n}.pdb'))

        return (seqs)