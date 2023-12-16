import itertools
import typing


def unsort_idxs(values: list[typing.Any]) -> list[int]:
    # Actually, the type of value must be "Comparable" (not "Any") but there is not built-in
    # support for that yet in Python
    idxs = list(range(len(values)))
    idxs.sort(key=values.__getitem__)

    return idxs


def sort(values: list[float]) -> tuple[list[float], list[int]]:
    return list(sorted(values)), unsort_idxs(values)


def unsort(values: list[float], idxs: list[int]) -> list[float]:
    original_ordered_values = [0.0] * len(values)

    for idx, value in zip(idxs, values):
        original_ordered_values[idx] = value

    return original_ordered_values


def distribute(coordinates: list[float], min_distance: float) -> list[float]:
    """
    Distribute the coordinates in such a way that the difference between each coordinate is
    at least greater or equal to a certain distance

    :param coordinates: List of coordinates
    :param min_distance: Minimum distance between two consecutive coordinates
    :return: List of coordinates satisfying the minimum distance criterion. If additional space is
        added between the coordinates, this is added evenly to both sides of the range of
        coordinates.
    """
    coordinates, idxs = sort(coordinates)

    assert sorted(coordinates) == coordinates, coordinates
    assert min_distance >= 0

    distributed_coordinates = []

    if len(coordinates) <= 1:
        distributed_coordinates = coordinates
    if len(coordinates) > 1:
        distances = []

        for lhs, rhs in itertools.pairwise(coordinates):
            current_distance = rhs - lhs
            if current_distance < min_distance:
                distances.append(current_distance)

        if len(distances) == 0:
            distributed_coordinates = coordinates
        else:
            distance_to_add = (len(distances) * min_distance) - sum(distances)
            half_distance_to_add = 0.5 * distance_to_add
            offset = -half_distance_to_add

            for lhs, rhs in itertools.pairwise(coordinates):
                current_distance = rhs - lhs
                lhs += offset

                if current_distance < min_distance:
                    offset += min_distance - current_distance

                distributed_coordinates.append(lhs)

            distributed_coordinates.append(coordinates[-1] + offset)

    distributed_coordinates = unsort(distributed_coordinates, idxs)

    return distributed_coordinates