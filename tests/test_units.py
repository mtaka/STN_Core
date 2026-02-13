"""Tests for stn_core.units."""

import stn
from stn_core.units import LeaderType, parse_chunks_to_statements


class TestParseStatements:
    def test_typedef_statement(self):
        r = stn.parse("@%Rect (x y w h)")
        stmts = parse_chunks_to_statements(r.ast)
        assert len(stmts) == 1
        assert stmts[0].is_define is True
        assert stmts[0].units[0].leader.kind == LeaderType.TypeCall
        assert stmts[0].units[0].operand == "Rect"
        assert stmts[0].units[0].child is not None

    def test_global_def_with_type(self):
        r = stn.parse("@#R1 %Rect(10 20 100 50)")
        stmts = parse_chunks_to_statements(r.ast)
        assert len(stmts) == 1
        assert stmts[0].is_define is True
        assert stmts[0].units[0].leader.kind == LeaderType.GlobalRef
        assert stmts[0].units[0].operand == "R1"
        assert stmts[0].units[1].leader.kind == LeaderType.TypeCall
        assert stmts[0].units[1].operand == "Rect"

    def test_getter(self):
        r = stn.parse("#R1.x")
        stmts = parse_chunks_to_statements(r.ast)
        assert len(stmts) == 1
        assert stmts[0].is_define is False
        assert stmts[0].units[0].leader.kind == LeaderType.GlobalRef
        assert stmts[0].units[1].leader.kind == LeaderType.Getter
        assert stmts[0].units[1].operand == "x"

    def test_setter_with_child(self):
        r = stn.parse("#R1!id(#01)")
        stmts = parse_chunks_to_statements(r.ast)
        assert len(stmts) == 1
        s = stmts[0]
        assert s.units[0].leader.kind == LeaderType.GlobalRef
        assert s.units[1].leader.kind == LeaderType.Setter
        assert s.units[1].operand == "id"
        assert s.units[1].child is not None

    def test_batch_setter(self):
        r = stn.parse("#R1!+(x 10 y 20)")
        stmts = parse_chunks_to_statements(r.ast)
        assert len(stmts) == 1
        s = stmts[0]
        assert s.units[1].leader.kind == LeaderType.Setter
        assert s.units[1].operand == "+"
        assert s.units[1].child is not None

    def test_multiple_statements(self):
        r = stn.parse("@%Rect (x y w h) ; @#R1 %Rect(10 20 100 50) ; #R1.x")
        stmts = parse_chunks_to_statements(r.ast)
        assert len(stmts) == 3
        assert stmts[0].is_define is True   # @%Rect
        assert stmts[1].is_define is True   # @#R1
        assert stmts[2].is_define is False  # #R1.x
