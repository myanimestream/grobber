__all__ = ["AsyncFormatter"]

import _string
from string import Formatter


class AsyncFormatter(Formatter):
    async def format(*args, **kwargs):
        if not args:
            raise TypeError("descriptor 'format' of 'Formatter' object "
                            "needs an argument")
        self, *args = args  # allow the "self" keyword be passed
        try:
            format_string, *args = args  # allow the "format_string" keyword be passed
        except ValueError:
            raise TypeError("format() missing 1 required positional "
                            "argument: 'format_string'") from None
        return await self.vformat(format_string, args, kwargs)

    async def vformat(self, format_string, args, kwargs):
        used_args = set()
        result, _ = await self._vformat(format_string, args, kwargs, used_args, 2)
        self.check_unused_args(used_args, args, kwargs)
        return result

    async def _vformat(self, format_string, args, kwargs, used_args, recursion_depth, auto_arg_index=0):
        if recursion_depth < 0:
            raise ValueError('Max string recursion exceeded')
        result = []
        for literal_text, field_name, format_spec, conversion in \
                self.parse(format_string):

            # output the literal text
            if literal_text:
                result.append(literal_text)

            # if there's a field, output it
            if field_name is not None:
                # this is some markup, find the object and do
                #  the formatting

                # handle arg indexing when empty field_names are given.
                if field_name == '':
                    if auto_arg_index is False:
                        raise ValueError('cannot switch from manual field '
                                         'specification to automatic field '
                                         'numbering')
                    field_name = str(auto_arg_index)
                    auto_arg_index += 1
                elif field_name.isdigit():
                    if auto_arg_index:
                        raise ValueError('cannot switch from manual field '
                                         'specification to automatic field '
                                         'numbering')
                    # disable auto arg incrementing, if it gets
                    # used later on, then an exception will be raised
                    auto_arg_index = False

                # given the field_name, find the object it references
                #  and the argument it came from
                obj, arg_used = await self.get_field(field_name, args, kwargs)
                used_args.add(arg_used)

                # do any conversion on the resulting object
                obj = self.convert_field(obj, conversion)

                # expand the format spec, if needed
                format_spec, auto_arg_index = await self._vformat(
                    format_spec, args, kwargs,
                    used_args, recursion_depth - 1,
                    auto_arg_index=auto_arg_index)

                # format the object and append to the result
                result.append(self.format_field(obj, format_spec))

        return ''.join(result), auto_arg_index

    async def get_value(self, key, args, kwargs):
        if isinstance(key, int):
            return args[key]
        else:
            return kwargs[key]

    # given a field_name, find the object it references.
    #  field_name:   the field being looked up, e.g. "0.name"
    #                 or "lookup[3]"
    #  used_args:    a set of which args have been used
    #  args, kwargs: as passed in to vformat
    async def get_field(self, field_name, args, kwargs):
        first, rest = _string.formatter_field_name_split(field_name)

        obj = await self.get_value(first, args, kwargs)

        # loop through the rest of the field_name, doing
        #  getattr or getitem as needed
        for is_attr, i in rest:
            if is_attr:
                obj = getattr(obj, i)
            else:
                obj = obj[i]

        return obj, first
