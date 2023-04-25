# This source code is part of the proteusAI package and is distributed
# under the MIT License.

__name__ = "proteusAI"
__author__ = "Jonathan Funk"

# Quick fix remove later
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

import torch
import torch.nn.functional as F
import esm
import os
from proteusAI.io_tools import fasta
import seaborn as sns
import pandas as pd
import matplotlib.pyplot as plt


def esm_compute(seqs: list, names: list=None, model: str="esm1v", rep_layer: int=33):
    """
    Compute the of esm models for a list of sequences.

    Parameters:
        seqs (list): protein sequences either as str or biotite.sequence.ProteinSequence.
        names (list, default None): list of names/labels for protein sequences.
            If None sequences will be named seq1, seq2, ...
        model (str): choose either esm2 or esm1v.
        rep_layer (int): choose representation layer. Default 33.

    Returns: representations (list) of sequence representation, batch lens and batch labels

    Example:
        seqs = ["AGAVCTGAKLI", "AGHRFLIKLKI"]
        results, batch_lens, batch_labels = esm_compute(seqs)
    """
    # detect device
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    # on M1 if mps available
    if device == torch.device(type='cpu'):
        device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')

    # load model
    if model == "esm2":
        model, alphabet = esm.pretrained.esm2_t48_15B_UR50D()
    elif model == "esm1v":
        model, alphabet = esm.pretrained.esm1v_t33_650M_UR90S()
    else:
        raise f"{model} is not a valid model"

    batch_converter = alphabet.get_batch_converter()
    model.eval()
    model.to(device)

    if names == None:
        names = [str(i) for i in range(len(seqs))]

    data = list(zip(names, seqs))

    # check datatype of sequences - str or biotite
    if all(isinstance(x[0], str) and isinstance(x[1], str) for x in data):
        pass  # all elements are strings
    else:
        data = [(x[0], str(x[1])) for x in data]

    batch_labels, batch_strs, batch_tokens = batch_converter(data)
    batch_lens = (batch_tokens != alphabet.padding_idx).sum(1)

    # Extract per-residue representations (on CPU)
    with torch.no_grad():
        results = model(batch_tokens.to(device), repr_layers=[rep_layer], return_contacts=True)

    return results, batch_lens, batch_labels, alphabet


def get_seq_rep(results, batch_lens):
    """
    Get sequence representations from esm_compute
    """
    token_representations = results["representations"][33]

    # Generate per-sequence representations via averaging
    sequence_representations = []
    for i, tokens_len in enumerate(batch_lens):
        sequence_representations.append(token_representations[i, 1: tokens_len - 1].mean(0))

    return sequence_representations


def get_logits(results):
    """
    Get logits from esm_compute
    """
    logits = results["logits"]
    return logits


def get_attentions(results):
    """
    Get attentions from esm_compute
    """
    attn = results["attentions"]
    return attn


def get_probability_distribution(logits):
    """
    Convert logits to probability distribution for each position in the sequence.
    """
    # Apply softmax function to the logits along the alphabet dimension (dim=2)
    probability_distribution = F.softmax(logits, dim=-1)

    return probability_distribution


def per_position_entropy(probability_distribution):
    """
    Compute the per-position entropy from a probability distribution tensor.
    """
    # Calculate per-position entropy using the formula: H(x) = -sum(p(x) * log2(p(x)))
    entropy = -torch.sum(probability_distribution * torch.log2(probability_distribution + 1e-9), dim=-1)

    return entropy

def batch_embedd(seqs: list=None, names: list=None, fasta_path: str=None, dest: str=None, model: str="esm1v", batch_size: int=10, rep_layer: int=33):
    """
    Computes and saves sequence representations in batches using esm2 or esm1v.

    Parameters:
        seqs (list): protein sequences either as str or biotite.sequence.ProteinSequence
        names (list, default None): list of names/labels for protein sequences
        fasta_path (str): path to fasta file.
        dest (str): destination where embeddings are saved. Default None (won't save if dest is None).
        model (str): choose either esm2 or esm1v
        batch_size (int): batch size. Default 10
        rep_layer (int): choose representation layer. Default 33.

    Returns: representations (list) of sequence representation.

    Example:
        1.
        seqs = ["AGAVCTGAKLI", "AGHRFLIKLKI"]
        batch_embedd(seqs=seqs, dest='path')

        2.
        batch_embedd(fasta_path='file.fasta', dest='path')
    """
    if dest == None:
        raise "No save destination provided."

    if fasta_path == None and seqs == None:
        raise "Either fasta_path or seqs must not be None"

    if fasta != None:
        names, seqs = fasta.load_all(fasta_path)

    for i in range(0, len(seqs), batch_size):
        results, batch_lens, batch_labels, alphabet = esm_compute(seqs[i:i + batch_size], names[i:i + batch_size], model=model, rep_layer=rep_layer)
        sequence_representations = get_seq_rep(results)
        if dest is not None:
            for j in range(len(sequence_representations)):
                _dest = os.path.join(dest, names[i:i + batch_size][j])
                torch.save(sequence_representations[j], _dest + '.pt')


def mask_positions(sequence: str, mask_char: str='<mask>'):
    """
    Mask every position of an amino acid sequence. Returns list of masked sequence:

    Parameters:
        sequence (str): Amino acid sequence
        mask_char (str): Character used for masking (default: <mask>)

    Returns:
        list: list of masked sequences

    Examples:
        sequence = 'AMGAT'
        seqs = mask_positions(sequence)
        ['<mask>MGAT', 'A<mask>GAT', ..., 'AMGA<mask>']
    """
    masked_sequences = []
    for i in range(len(sequence)):
        masked_seq = sequence[:i] + mask_char + sequence[i+1:]
        masked_sequences.append(masked_seq)

    return masked_sequences


def mut_prob(seq: str, model: str="esm1v", batch_size: int=10, rep_layer: int=33, alphabet_size: int=33):
    """
    Compute mutation probabilities based on masked sequence modelling using esm1v or esm2.
    Every position of a sequence will be masked and the probability for every amino acid at that
    position will be stored. The probabilities for every position will be concatenated in a tensor.

    Parameters:
        seq (str): native protein sequence
        model (str): choose either esm2 or esm1v
        batch_size (int): batch size. Default 10
        rep_layer (int): choose representation layer. Default 33.

    Returns:
        Logits torch.Tensor for every position and alphabet

    Example:
        1.
        seq = "AGHRFLIKLKI"
        logits = mut_prob(seq=seq)

        2.
        batch_embedd(fasta_path='file.fasta', dest='path')
    """
    masked_seqs = mask_positions(seq)
    names = [f'seq{i}' for i in range(len(masked_seqs))]
    sequence_length = len(seq)

    # Initialize an empty tensor of the desired shape
    logits_tensor = torch.zeros(1, sequence_length, alphabet_size)

    for i in range(0, len(masked_seqs), batch_size):
        results, batch_lens, batch_labels, alphabet = esm_compute(masked_seqs[i:i + batch_size],
                                                                  names[i:i + batch_size], model=model,
                                                                  rep_layer=rep_layer)
        logits = results["logits"]

        # Fill the logits_tensor with the logits for each masked position
        for j in range(logits.shape[0]):
            masked_position = i + j
            if masked_position < sequence_length:
                logits_tensor[0, masked_position] = logits[j, masked_position + 1]

    p = get_probability_distribution(logits_tensor)

    return p, alphabet


def most_likely_sequence(log_prob_tensor, alphabet):
    """
    Get the most likely amino acid sequence based on log probabilities.

    Parameters:
        log_prob_tensor (torch.Tensor): Tensor of shape (1, sequence_length, alphabet_size) containing log probabilities
        alphabet (dict or esm.data.Alphabet): Dictionary mapping indices to characters

    Returns:
        str: Most likely amino acid sequence
    """
    if type(alphabet) == dict:
        pass
    else:
        try:
            alphabet = alphabet.to_dict()
        except:
            raise "alphabet has an unexpected format"

    # Find the indices of the maximum log probabilities along the alphabet dimension
    max_indices = torch.argmax(log_prob_tensor, dim=-1).squeeze()

    # Filter the alphabet dictionary to only include cannonical AAs
    include = ['A', 'R', 'N', 'D', 'C', 'Q', 'E', 'G', 'H', 'I', 'L', 'K', 'M', 'F', 'P', 'S', 'T', 'W', 'Y', 'V']
    filtered_alphabet = {char: i for char, i in alphabet.items() if char in include}

    # Map the indices back to their corresponding amino acids using the alphabet dictionary
    most_likely_seq = ''.join([filtered_alphabet[int(idx)] for idx in max_indices])

    return most_likely_seq


def find_mutations(native_seq, predicted_seq):
    """
    Find the mutations between the native protein sequence and the predicted most likely sequence.

    Parameters:
        native_seq (str): Native protein sequence
        predicted_seq (str): Predicted most likely protein sequence

    Returns:
        list: List of mutations in the format ['G2A', 'F4H']
    """

    if len(native_seq) != len(predicted_seq):
        raise ValueError("Native and predicted sequences must have the same length")

    mutations = []

    for i, (native_aa, predicted_aa) in enumerate(zip(native_seq, predicted_seq)):
        if native_aa != predicted_aa:
            mutation = f"{native_aa}{i+1}{predicted_aa}"
            mutations.append(mutation)

    return mutations


def plot_probability(p, alphabet, include="canonical", remove_tokens=True, dest=None, show=True):
    """
    Plot a heatmap of the probability distribution for each position in the sequence.

    Parameters:
        p (torch.Tensor): probability_distribution torch.Tensor with shape (1, sequence_length, alphabet_size)
        alphabet (dict or esm.data.Alphabet): Dictionary mapping indices to characters
        include (str or list): List of characters to include in the heatmap (default: canonical, include only canonical amino acids)
        dest (str): Optional path to save the plot as an image file (default: None)
        show (bool): Boolean controlling whether the plot is shown (default: True)

    Returns:
        None
    """

    if type(alphabet) == dict:
        pass
    else:
        try:
            alphabet = alphabet.to_dict()
        except:
            raise "alphabet has an unexpected format"

    # Convert the probability distribution tensor to a numpy array
    probability_distribution_np = p.cpu().numpy().squeeze()

    # Remove the start and end of sequence tokens
    if remove_tokens:
        probability_distribution_np = probability_distribution_np[1:-1, :]

    # If no characters are specified, include only amino acids by default
    if include == "canonical":
        include = ['A', 'R', 'N', 'D', 'C', 'Q', 'E', 'G', 'H', 'I', 'L', 'K', 'M', 'F', 'P', 'S', 'T', 'W', 'Y', 'V']
    elif include == "all":
        include = alphabet.keys()
    elif type(alphabet) == list:
        include = include
    else:
        raise "include must either be 'canonical' 'all' or a list of valid elements"

    # Filter the alphabet dictionary based on the 'include' list
    filtered_alphabet = {char: i for char, i in alphabet.items() if char in include}

    # Create a pandas DataFrame with appropriate column and row labels
    df = pd.DataFrame(probability_distribution_np[:, list(filtered_alphabet.values())],
                      columns=[i for i in filtered_alphabet.keys()])

    # Create a heatmap using seaborn
    plt.figure(figsize=(20, 6))
    sns.heatmap(df.T, cmap="Reds", linewidths=0.5, annot=False, cbar=True)
    plt.xlabel("Sequence Position")
    plt.ylabel("Character")
    plt.title("Per-Position Probability Distribution Heatmap")

    # Save the plot to the specified destination, if provided
    if dest is not None:
        plt.savefig(dest, dpi=300, bbox_inches='tight')

    # Show the plot, if the 'show' argument is True
    if show:
        plt.show()

seq = "GAAEAGITGTWYNQLGSTFIVTAGADGALTGTYESAVGNAESRYVLTGRYDSAPATDGSGTALGWTVAWKNNYRNAHSATTWSGQYVGGAEARINTQWLLTSGTTEANAWKSTLVGHDTFTKVKPSAAS"

p, alphabet = mut_prob(seq)
pred_seq = most_likely_sequence(p, alphabet)
mutations = find_mutations(seq, pred_seq)

with open('test', 'w') as f:
    print(p, file=f)
    print(seq, file=f)
    print(pred_seq, file=f)
    print(mutations, file=f)

plot_probability(p=p, alphabet=alphabet, dest='heat.png', remove_tokens=False)