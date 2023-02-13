import torch
import esm
import os
import time
import argparse
import sys
sys.path.append('../')
from io_tools import fasta

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
# on M1 if mps available
if device == torch.device(type='cpu'):
    device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')

print('Using device:', device)

# Load ESM-2 model
model, alphabet = esm.pretrained.esm2_t33_650M_UR50D()
model.to(device)
model.eval()  # disables dropout for deterministic results

batch_converter = alphabet.get_batch_converter()

def compute_representations(data: list, dest: str = None, device: str = 'cuda'):
    '''
    generate sequence representations using esm2_t33_650M_UR50D.
    The representation are of size 1280.

    Parameters:
        data (list): list of tuples containing sequence labels (str) and protein sequences 
                     (str or biotite.sequence.ProteinSequence) (label, sequence)
        dest (str): destination where embeddings are saved. Default None (won't save if dest is None).
        device (str): device used for calculation or representations. Default "cuda". 
                      other options are "cpu", or "mps" for M1/M2 chip

    Returns: representations (list)

    Example:
        data = [("protein1", "AGAVCTGAKLI"), ("protein2", "AGHRFLIKLKI")]
        representations = get_sequence_representations(data)

    '''
    # check datatype of data
    if all(isinstance(x[0], str) and isinstance(x[1], str) for x in data):
        pass # all elements are strings
    else:
        data = [(x[0], str(x[1])) for x in data]
    
    batch_labels, batch_strs, batch_tokens = batch_converter(data)
    batch_lens = (batch_tokens != alphabet.padding_idx).sum(1)

    with torch.no_grad():
        results = model(batch_tokens.to(device), repr_layers=[33], return_contacts=True)

    token_representations = results["representations"][33]

    # Generate per-sequence representations via averaging
    # NOTE: token 0 is always a beginning-of-sequence token, so the first residue is token 1.
    sequence_representations = []
    for i, tokens_len in enumerate(batch_lens):
        sequence_representations.append(token_representations[i, 1: tokens_len - 1].mean(0))

    if dest is not None:
        for i in range(len(sequence_representations)):
            _dest = os.path.join(dest, batch_labels[i])
            torch.save(sequence_representations[i], _dest + '.pt')

    return sequence_representations


def divide_list(lst, chunk_size):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


def batchify_fasta(fasta_path: str, batch_size: int):
    """
    Get batches from fasta file with format:
    >{index}|{id}|{activity}
    {Sequence}

    Parameters:
        fasta_path : path to fasta file
        batch_size : batch size for calculation of representations
        dest : destination for saved embeddings. If dest=None embeddings won't be saved

    Returns: three list objects
        [(sequence_label, sequence)], activities
    """
    with open(fasta_path, 'r') as f:
        activities = []
        data = []
        batch = []
        for line in f:
            if line.startswith('>'):
                label = line.split('|')[1]
                activity = float(line.split('|')[2].replace('\n', ''))
            else:
                fasta = line.replace('\n', '')
                activities.append(activity)
                data.append((label, fasta))

        batches = []
        for chunk in divide_list(data, batch_size):
            batches.append(chunk)

        _activities = []
        for chunk in divide_list(activities, batch_size):
            _activities.append(chunk)

        return batches, _activities

def extract_sequences(file_name):
    """
    Given a fasta file with the format:

    >name1
    sequence1
    >name2
    sequence2

    this function will return the names and sequences of the fasta as lists.

    Parameters:
        file_name (str): name and path to file

    Returns:
        tuple: (names [list], sequences [list])
    """
    names = []
    sequences = []
    with open(file_name, 'r') as f:
        current_sequence = ""
        for line in f:
            line = line.strip()
            if line.startswith(">"):
                if current_sequence:
                    sequences.append(current_sequence)
                names.append(line[1:])
                current_sequence = ""
            else:
                current_sequence += line
        sequences.append(current_sequence)
    return names, sequences
    

### TODO: FROM HERE MOVE TO SCRIPTS SECTION AND IMPORT RELEVANT SCRIPTS###
def batch_embedd(fasta_path: str, dest: str, batch_size: int = 10):
    """
    takes fasta files in a specific format and embedds all the sequences using the 
    esm2_t33_650M_UR50D model. The embeddings are saved in the destination folder.
    Fasta format:
    
        >{index}|{id}|{activity}
        {Sequence}
        >{index}|{id}|{activity}
        {Sequence}
    
    Parameters:
        fasta_path (str): path to fasta file
        dest (str): destination
        batch_size (int)

    Returns:
        list of sequence representations
    """

    if not os.path.exists(dest):
        os.makedirs(dest)

    start_time = time.time()
    batches, activities = batchify_fasta(fasta_path=fasta_path, batch_size=batch_size)

    for batch in batches:
        _ = compute_representations(batch, dest=dest, device=device)
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(elapsed_time)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=
     '''
     Description:
     Creates embeddings for a fasta file using esm.pretrained.esm2_t33_650M_UR50D() 
     and saves them at the destination.
     
     if the activity flag (-a or --activity) flag is set, the fasta should have the
     following format:
         >{index}|{id}|{activity}
         {Sequence}
     
     saves files as:
     <path to dest>/{id}.pt
     
     example:
     python3 embedd.py -f input.fasta -d out_dir -b 26
     ''',
    formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument('-f', '--fasta', help='path to fasta file', required=True, default=None)
    parser.add_argument('-d', '--dest', help='path to destination', required=True, default=None)
    parser.add_argument('-b', '--batch_size', help='batch size for computation of representations', default=26)
    parser.add_argument('-a', '--activity', help='Set true if activity values are provided', default=False)
    args = parser.parse_args()


    FASTA_PATH = args.fasta
    DEST = args.dest
    BATCH_SIZE = int(args.batch_size)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    # on M1 if mps available
    if device == torch.device(type='cpu'):
        device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')

    print('Using device:', device)

    # Load ESM-2 model
    model, alphabet = esm.pretrained.esm2_t33_650M_UR50D()
    model.to(device)
    model.eval()  # disables dropout for deterministic results

    if args.activity:
        batch_converter = alphabet.get_batch_converter()
        batch_embedd(FASTA_PATH, DEST, BATCH_SIZE)
    else:
        names, seqs = extract_sequences(FASTA_PATH)
        data = list(zip(names, seqs))
        for i in range(0, len(data), BATCH_SIZE):
            r = compute_representations(data[i:i + BATCH_SIZE], dest=DEST, device=str(device))