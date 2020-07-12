from schema import Schema

userRegistrationSchema = Schema({'user_email': str,
                                 'user_id': str,
                                 'user_password': str,
                                 'board_id': str})

gamePlaySchema = Schema({'game_id': str,
                         'to': str,
                         'from': str, })
