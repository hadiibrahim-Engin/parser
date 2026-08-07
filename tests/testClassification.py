import pytest

from cgmes2excel.domain.classification import (
    DEFAULT_ELEMENT_CLASSES,
    ElementCategory,
    EquipmentRegistry,
    UnknownEquipmentClassError,
)


def testBranchEquipmentIsIncludedByDefault():
    registry = EquipmentRegistry.withDefaults()
    assert registry.isIncluded("ACLineSegment")
    assert registry.isIncluded("PowerTransformer")


def testSwitchgearIsKnownButNotIncludedByDefault():
    registry = EquipmentRegistry.withDefaults()
    assert registry.isKnown("Breaker")
    assert not registry.isIncluded("Breaker")


def testAclineSegmentIsCategorisedAsABranch():
    registry = EquipmentRegistry.withDefaults()
    assert registry.kindFor("ACLineSegment").category is ElementCategory.BRANCH


def testPowerTransformerHasItsOwnCategory():
    registry = EquipmentRegistry.withDefaults()
    assert registry.kindFor("PowerTransformer").category is ElementCategory.TRANSFORMER


def testSinglyConnectedEquipmentIsCategorisedAsInjection():
    registry = EquipmentRegistry.withDefaults()
    assert registry.kindFor("EnergyConsumer").category is ElementCategory.INJECTION
    assert registry.kindFor("SynchronousMachine").category is ElementCategory.INJECTION


def testBusbarSectionHasItsOwnCategory():
    registry = EquipmentRegistry.withDefaults()
    assert registry.kindFor("BusbarSection").category is ElementCategory.BUSBAR


def testUnknownClassRaisesRatherThanGuessingACategory():
    registry = EquipmentRegistry.withDefaults()
    with pytest.raises(UnknownEquipmentClassError):
        registry.kindFor("PetrolGenerator")


def testUnknownClassIsNeitherKnownNorIncluded():
    registry = EquipmentRegistry.withDefaults()
    assert not registry.isKnown("PetrolGenerator")
    assert not registry.isIncluded("PetrolGenerator")


def testAdditionalClassesCanBeSwitchedOn():
    registry = EquipmentRegistry.withDefaults().including("Breaker", "BusbarSection")
    assert registry.isIncluded("Breaker")
    assert registry.isIncluded("BusbarSection")
    assert registry.isIncluded("ACLineSegment")


def testTheIncludedSetCanBeReplacedOutright():
    registry = EquipmentRegistry.withDefaults().onlyIncluding("Breaker")
    assert registry.isIncluded("Breaker")
    assert not registry.isIncluded("ACLineSegment")


def testIncludingAnUnknownClassRegistersItAsGenericEquipment():
    registry = EquipmentRegistry.withDefaults().including("PetrolGenerator")
    assert registry.isIncluded("PetrolGenerator")
    assert registry.kindFor("PetrolGenerator").category is ElementCategory.OTHER


def testIncludedClassesAreReportedInAStableOrder():
    registry = EquipmentRegistry.withDefaults().including("Breaker")
    assert registry.includedClasses() == sorted(registry.includedClasses())


def testDefaultIncludedSetIsBranchOrientedAndPubliclyVisible():
    assert "ACLineSegment" in DEFAULT_ELEMENT_CLASSES
    assert "PowerTransformer" in DEFAULT_ELEMENT_CLASSES
    assert "Breaker" not in DEFAULT_ELEMENT_CLASSES


def testExpectedTerminalCountIsKnownPerCategory():
    registry = EquipmentRegistry.withDefaults()
    assert registry.kindFor("ACLineSegment").expectedTerminals == 2
    assert registry.kindFor("EnergyConsumer").expectedTerminals == 1
    assert registry.kindFor("BusbarSection").expectedTerminals == 1
    assert registry.kindFor("PowerTransformer").expectedTerminals is None


def testRegistryIsNotMutatedByDerivingAVariant():
    base = EquipmentRegistry.withDefaults()
    base.including("Breaker")
    assert not base.isIncluded("Breaker")
